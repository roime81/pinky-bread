# Pinky Bread

**Pinky Bread 2.0 — Local-first AI Company Operating System**

Pinky Bread is evolving from a multi-agent workflow prototype into a founder-led virtual company. A founder defines the company vision, mission, goals and KPIs; a persistent company graph connects AI employees, assignments, meetings, decisions, deliverables and business outcomes. The graph is the primary workspace and a live projection of database records and company events.

Pinky Bread 2.0 Alpha 4 packages the durable workforce as a local-first runtime: Ollama starts by default, the selected model is pulled automatically, API and MCP have dedicated host ports, and Docker service DNS keeps container-to-container calls predictable. PostgreSQL stores jobs and LangGraph checkpoints; worker leases, heartbeats and recovery allow execution to resume after process loss. Valkey coordinates worker wake-ups, the founder can enable recurring Head-of-Agents coordination, and the official MCP Python SDK v2 connects role-scoped tools to self-hosted Ollama/vLLM-compatible model APIs.

> **Versioning:** this release is **Pinky Bread 2.0.0 Alpha 4** (`v2.0.0-alpha.4`), built on the Alpha 1 company graph, Alpha 2 workforce runtime and Alpha 3 durable runtime. The default `main` branch is the source of truth. See the [Alpha 4 release notes](docs/releases/v2.0.0-alpha.4.md), the [changelog](CHANGELOG.md), [2.0 architecture](docs/ARCHITECTURE_2.0.md), [open-source stack](docs/OPEN_SOURCE_STACK_2.0.md) and [delivery roadmap](docs/ROADMAP_2.0.md).

> [!IMPORTANT]
> **MVP / demonstration software.** Docker Compose uses live local Ollama inference by default; mock inference is available only when explicitly enabled and does not inspect image pixels. The included refund/ledger action is simulated and never contacts a real banking system or transfers money. Local development sign-in and Google OAuth sign-in are available, but enterprise RBAC, company membership/tenant isolation, production identity lifecycle, production MCP OAuth/JWT verification, production-grade PII detection and independently immutable audit storage are not implemented. Do not use this build for production, regulated decisions, or real financial/clinical operations.

---

## Contents

- [Pinky Bread 2.0 Alpha 4](#pinky-bread-20-alpha-4)
- [Release notes](docs/releases/v2.0.0-alpha.4.md)
- [Changelog](CHANGELOG.md)
- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Requirements](#requirements)
- [Install and run with Docker Compose](#install-and-run-with-docker-compose)
- [Optional standalone Python / Uvicorn mode](#optional-standalone-python--uvicorn-mode)
- [Local service ports](#local-service-ports)
- [Configure the Ollama model](#configure-the-ollama-model)
- [Configuration reference](#configuration-reference)
- [Try the demo workflow](#try-the-demo-workflow)
- [API reference](#api-reference)
- [Configure specialist agents](#configure-specialist-agents)
- [Run tests](#run-tests)
- [Project structure](#project-structure)
- [Security and operational boundaries](#security-and-operational-boundaries)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)

## Pinky Bread 2.0 Alpha 4

### What is new

- **Living Company Graph:** the default workspace visualises the company, goals, KPI nodes, agent identities, work, meetings, decisions and deliverables as connected dots.
- **Persistent company data model:** PostgreSQL-backed node, relationship and event records. A single agent identity can connect to multiple goals and assignments.
- **Founder-defined workforce:** companies start with an empty agent roster. Create any agent you need with a custom role, title, skills, responsibilities, system instructions, seniority, authority and reporting line.
- **Interactive graph:** add goal, KPI, agent, work and meeting records; connect dots; select any node to inspect its data and relationships. Upload company documents and deliverables, link them to goals/work and download them through company-scoped artifact endpoints.
- **Company event history:** append-only hash-linked records, paginated history and a hash-chain verification endpoint.
- **Live graph notifications:** Valkey Pub/Sub pushes committed graph events to connected clients; PostgreSQL remains the durable source of truth.
- **Open object storage path:** workflow attachments and company documents/deliverables use a local or S3-compatible adapter. PostgreSQL catalogs ownership, company/tenant scope, checksum, type, size and object key; SeaweedFS stores the bytes in Compose.
- **Open-source Compose stack:** PostgreSQL 16 with pgvector, Valkey and SeaweedFS.
- **Agent lifecycle management:** create, edit, promote, demote and remove custom agents. Agent removal archives the identity while preserving previous assignments, deliverables and audit history.
- **Dynamic goal-to-work execution:** the founder-selected coordinator delegates to the active agents defined in that company. The planner can only assign work to real agent IDs from the company's roster.
- **Stored work products:** each successful assignment writes a Markdown deliverable to local/S3 object storage; PostgreSQL records metadata, ownership and checksum, and the graph links work to its output.
- **Virtual meetings:** turn-based text discussions with participant edges, contributions, facilitator summary and stored minutes.
- **Agent-to-agent conversations (new feature branch):** named agents can initiate real peer messages, receive replies through each colleague's own persona/model configuration, persist the exchange in PostgreSQL, stream the timeline to a React workspace and return a founder-facing summary. See [A2A runtime documentation](docs/AGENT_TO_AGENT_2.0.md).
- **KPI history:** founder-recorded numeric measurements with source, evidence, timestamp and a bounded snapshot history.
- **Durable jobs:** PostgreSQL job rows with idempotency, worker ownership leases, heartbeats, retries/backoff, cancellation and expired-lease recovery.
- **LangGraph checkpoints:** each durable job runs through a LangGraph StateGraph with PostgreSQL AsyncPostgresSaver checkpoints keyed by job ID.
- **Valkey coordination:** best-effort wake-up notifications; workers poll PostgreSQL as a loss-safe fallback.
- **Continuous coordination:** the founder-selected coordinator can run recurring PLAN_ONLY or AUTO_EXECUTE schedules; disabled by default.
- **Official MCP v2:** Streamable HTTP MCP server/client, tool discovery, per-role allow-list and runtime-injected company/tenant/agent identity. MCP is published on a dedicated host port for private local integrations.
- **Default private LLM:** Ollama starts with the Compose stack, pulls `qwen2.5:3b` on first startup and stores model files in a persistent Docker volume. vLLM and other OpenAI-compatible local endpoints remain configurable.
- **Durable worker service:** separate worker process that can be scaled horizontally.

### What still needs to be built

Alpha 4 is a local-first durable workforce release, not yet a production-ready company. Job execution is checkpointed and recovers expired leases, but cancellation is cooperative at safe boundaries rather than interrupting an in-flight model generation. Meetings remain text-based; calendar scheduling and voice/video are not implemented. KPI measurements remain manual. No external MCP side-effect tools are enabled.

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
| Web operations console | Company graph, company onboarding, node inspector, relationships, event activity, legacy workflow/approval/agent/audit views, local development and Google sign-in | Development UI; authentication does not yet provide company membership, RBAC or tenant isolation |
| Company graph and workforce | Company, goals, KPIs, reusable agents, assignments, meetings and deliverables with typed edges | Durable PostgreSQL job queue, LangGraph checkpoints and worker recovery; authenticated tenant boundary remains future work |
| Company event history | PostgreSQL append-only company events with SHA-256 chaining and verification API | Tamper-evident, not independently immutable or WORM protected |
| Live graph updates | Valkey Pub/Sub notifications and SSE | Database event history is authoritative; Valkey notifications are best-effort |
| Object storage | Local filesystem or S3-compatible SeaweedFS for source documents, generated deliverables and meeting minutes | PostgreSQL catalogues owner, company/tenant, checksum and object key; auth/retention policies remain planned |
| Declarative agent registry | YAML manifests, Pydantic validation, reload endpoint | Registry reload is local configuration, not a governed deployment pipeline |
| Deterministic routing | Router plus explicit specialist hand-off logic | Lightweight Python state machine, not LangGraph |
| Local LLM integration | Ollama by default; vLLM/other OpenAI-compatible endpoints optional | Endpoint compatibility depends on the selected model/server |
| Mock inference | GPU-free deterministic development response | Does not understand or OCR image contents |
| Multimodal artifact intake | PNG/JPEG/PDF uploads, artifact persistence, PDF text extraction, image forwarding to configured vision endpoint | Scanned PDF OCR is not included; mock mode does not inspect images |
| Human-in-the-loop | Pending approval state, approve/reject API, approver ID and notes in audit | Approver ID is supplied by the caller; not authenticated |
| Tool access control | Agent manifest allow-list plus MCP v2 role-scoped tools | Static development bearer verifier; production identity remains future work |
| Audit trail | SHA-256 input hashes and previous-event hash links | Tamper-evident linkage, not WORM/immutable storage or signed audit |
| Persistence | PostgreSQL company graph, durable jobs and LangGraph checkpoints; SQLite for standalone mode | Compose migration bootstrap is provided; production migration governance remains future work |
| Container deployment | Docker Compose with API, worker, MCP, Ollama, PostgreSQL/pgvector, Valkey and SeaweedFS | Development credentials are in Compose; replace them before shared deployment |

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
| Frontend | Existing HTML/CSS/JavaScript shell + React 18, TypeScript, Vite, Framer Motion and Lucide React for Agent Conversations | The company graph and Alpha 4 screens remain in the existing shell; the A2A workspace is built to static assets and served by FastAPI |
| Object storage | SeaweedFS S3 API + boto3 | S3-compatible company documents, deliverables, meeting minutes and workflow artifacts |
| Containers | Docker, Docker Compose | Local container deployment |
| Tests | pytest, FastAPI TestClient | API and workflow behavior tests |

## Requirements

### Recommended Docker Compose deployment

- Docker Engine or Docker Desktop with Docker Compose v2
- Internet access on first startup to pull container images and the configured Ollama model
- Sufficient disk space and memory for PostgreSQL, Valkey, SeaweedFS, the API/worker and the selected model
- A GPU is optional. Ollama can run on CPU, although inference may be slower

### Optional standalone Python deployment

- Python 3.11 or newer and `pip`
- A local Ollama installation listening on `127.0.0.1:11434`, or another OpenAI-compatible model server
- Supporting services such as PostgreSQL, Valkey, MCP, the worker and object storage are **not** started by Uvicorn. Standalone mode is intended for API-only development.

## Install and run with Docker Compose

**Docker Compose is the recommended way to run Pinky Bread.** It starts the API, web UI, durable worker, MCP server, PostgreSQL, Valkey, SeaweedFS and Ollama together. It also runs the database migration and model-bootstrap services in the correct order.

You do not need to start Uvicorn, Ollama, PostgreSQL, Valkey, MCP or the worker in separate terminals when using this method.

### Existing checkout or GitHub Codespaces

Run these commands from the repository directory to update to the latest `main` branch and start the full application:

```bash
git switch main
git pull origin main
docker compose up --build -d
docker compose ps
```

### First-time installation

Clone the repository, then run the same startup commands:

```bash
git clone https://github.com/roime81/pinky-bread.git
cd pinky-bread
git switch main
git pull origin main
docker compose up --build -d
docker compose ps
```

### Optional environment configuration

The Compose defaults are suitable for a private local development environment. To customise settings such as Google OAuth, the session secret, model name or host binding, create a local environment file once:

```bash
cp .env.example .env
```

Do not overwrite an existing `.env` when updating the repository; it may contain your own credentials and settings.

For GitHub Codespaces, set `PB_BIND_ADDRESS=0.0.0.0` in `.env` when needed for forwarded ports. On a normal local machine, keep the default `127.0.0.1` binding. Avoid forwarding database, cache, MCP and Ollama ports publicly.

### Open the application

- Local browser: <http://localhost:8888>
- GitHub Codespaces: open port `8888` in the Codespaces **Ports** panel and open its forwarded URL.

The first startup can take longer because Docker must download the images and Ollama must pull the configured model. Check service startup and model download with:

```bash
docker compose ps
docker compose logs -f api worker ollama ollama-init
```

For local development, the default sign-in is:

- Username: `admin`
- Password: `admin`

Change these credentials and the session secret before sharing the environment. See [Sign in to Pinky Bread](#sign-in-to-pinky-bread) and [Enable Google sign-in](#enable-google-sign-in) for authentication setup.

### Update an existing installation

Use this sequence whenever you want to pull the latest code and rebuild the running services:

```bash
git switch main
git pull origin main
docker compose up --build -d
docker compose ps
```

Docker Compose recreates services when their image or configuration changes. Your PostgreSQL, model and uploaded-file data are stored in persistent volumes/directories. Use `docker compose down` to stop the stack; **do not add `--volumes` unless you intentionally want to delete persisted data**.

## Optional standalone Python / Uvicorn mode

Use this mode only when you deliberately want to run the FastAPI application directly on your host instead of using the Compose API service. It does **not** start the durable worker, MCP server, PostgreSQL, Valkey, SeaweedFS or Ollama. Those services must be configured and started separately when your development task needs them.

From the repository root, install the Python dependencies and start the API:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8888
```

Open <http://localhost:8888>. The `--reload` option is for development. Binding to `0.0.0.0` exposes the development server on all network interfaces; use it only on a trusted/private network.

**Do not run this Uvicorn command while Docker Compose is running its API service on port `8888`.** Choose one run mode at a time. To switch from Compose to standalone, stop the Compose stack first with `docker compose down`.

### Local service ports

| Service | Host port / URL | Container DNS / port | Purpose |
|---|---|---|---|
| Pinky Bread UI + API | `127.0.0.1:8888` | `api:8080` | Web app, REST API and OpenAPI docs |
| MCP Streamable HTTP | `127.0.0.1:8060/mcp` | `mcp:8090/mcp` | Private MCP integration endpoint |
| Ollama | `127.0.0.1:11434` | `ollama:11434` | Private local LLM inference |
| PostgreSQL | `127.0.0.1:5433` | `postgres:5432` | Company data, jobs and LangGraph checkpoints |
| Valkey | `127.0.0.1:6380` | `valkey:6379` | Notifications and worker wake-ups |
| SeaweedFS S3 | `127.0.0.1:8333` | `seaweedfs:8333` | Local object/document storage |

`PB_BIND_ADDRESS` controls the host-side listener for these published ports. It defaults to `127.0.0.1`. In Codespaces, set it to `0.0.0.0` if the forwarded-port proxy cannot reach loopback-bound Docker ports. Do not make database, cache, MCP or Ollama ports public.

### Host access versus Docker DNS

Host tools and browsers use `127.0.0.1` and the published host ports. Containers must use Docker service names because `localhost` inside a container refers only to that same container:

- API and worker → Ollama: `http://ollama:11434/v1`
- API and worker → MCP: `http://mcp:8090/mcp`
- API and worker → PostgreSQL: `postgres:5432`
- API and worker → Valkey: `valkey:6379`
- API and worker → SeaweedFS: `http://seaweedfs:8333`

Do not put `127.0.0.1:11434` into a container's model endpoint. Compose uses the separate `REASONING_CONTAINER_API_URL` variable for its internal Ollama address.

### Model bootstrap and first startup

The default is `MODEL_PROVIDER=ollama`, `MOCK_INFERENCE=false` and `REASONING_MODEL=qwen2.5:3b`. The one-shot `ollama-init` service checks `/api/tags`, pulls the configured model when missing, and completes before API/worker startup. Model files persist in the `ollama_data` volume, so they are not downloaded on every restart.

```bash
# Watch model download and service startup
docker compose logs -f ollama ollama-init api worker

# Confirm the API is not in mock mode
docker compose exec api printenv MOCK_INFERENCE
docker compose exec worker printenv MOCK_INFERENCE

# List locally installed Ollama models
curl http://127.0.0.1:11434/api/tags

# Check the API health endpoint
curl http://127.0.0.1:8888/api/healthz
```

To choose another Ollama model, change `REASONING_MODEL` in `.env` and run `docker compose up --build -d`. Check the model's memory requirements and licence before using it.

### Useful Compose operations

```bash
docker compose ps
docker compose logs -f api worker mcp
docker compose logs -f ollama ollama-init
docker compose exec ollama ollama list
docker compose up -d --scale worker=3
docker compose down

# Destructive: also removes PostgreSQL, Valkey, SeaweedFS and Ollama model volumes
docker compose down --volumes
```

`docker compose down` preserves named data volumes. Do not use `--volumes` unless you intend to delete persisted company data and downloaded model files.

### Optional standalone Python mode

Use this only when you intentionally do not want the Compose worker/data stack. First install and start Ollama on the host, then:

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8888
```

Open <http://127.0.0.1:8888>. In this mode the API uses the SQLite/local-file settings from `.env`; `MCP_ENABLED=false` means the MCP server is not part of this standalone command. Do not also run Uvicorn when the Compose `api` service is already running.

## Configure the Ollama model

These are the model settings in `.env`:

```dotenv
MOCK_INFERENCE=false
MODEL_PROVIDER=ollama
REASONING_API_URL=http://127.0.0.1:11434/v1
REASONING_CONTAINER_API_URL=http://ollama:11434/v1
REASONING_MODEL=qwen2.5:3b
VLLM_API_KEY=ollama
```

`REASONING_API_URL` is the host-run endpoint. Docker Compose overrides the application container endpoint using `REASONING_CONTAINER_API_URL`. For vLLM or another OpenAI-compatible endpoint, set `MODEL_PROVIDER` to `vllm` or `openai-compatible`, configure the endpoint reachable from the API and worker containers, set `REASONING_MODEL`, and provide `VLLM_API_KEY` when the server requires one.

Agent manifests may override the provider, model name and endpoint per employee. An empty agent-specific endpoint inherits the workspace endpoint.

### Multimodal model

`MULTIMODAL_API_URL` and `MULTIMODAL_MODEL` are optional endpoints for a separately deployed OpenAI-compatible vision model. This Compose stack does not start a vision server. Text-based PDFs are extracted locally; scanned-PDF OCR is not included. Mock mode does not inspect image pixels.



## Try the demo workflow

1. Start the application and open <http://127.0.0.1:8888>.
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
| `GET` | `/v2/companies/{company_id}/agents` | List the company's user-defined agent roster |
| `POST` | `/v2/companies/{company_id}/agents` | Create an agent with a custom role, persona, seniority and reporting line |
| `PATCH` | `/v2/companies/{company_id}/agents/{agent_id}` | Edit identity, instructions, seniority, authority or manager |
| `POST` | `/v2/companies/{company_id}/agents/{agent_id}/promote` | Increase seniority by one level |
| `POST` | `/v2/companies/{company_id}/agents/{agent_id}/demote` | Decrease seniority by one level |
| `DELETE` | `/v2/companies/{company_id}/agents/{agent_id}` | Archive an agent while preserving company history |
| `POST` | `/v2/companies/{company_id}/workforce/bootstrap` | Legacy-compatible roster discovery; does not create default agents |
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
curl -X POST http://127.0.0.1:8888/v1/workflows/invoke \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Review a cancelled flight and prepare a refund proposal for RM450."}'
```

### Approve a pending workflow

Replace `<THREAD_ID>` with the `thread_id` returned by the invoke endpoint:

```bash
curl -X POST http://127.0.0.1:8888/v1/workflows/<THREAD_ID>/approve \
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

The `.env.example` file is the canonical template. Copy it to `.env` once and edit `.env`; do not overwrite an existing `.env` when upgrading because it may contain your own tokens or settings.

### Application and model

| Variable | Default / effective value | Description |
|---|---|---|
| `APP_NAME` | `Pinky Bread` | Application title and API metadata. |
| `APP_ENV` | `development` standalone; `docker` in Compose | Environment label. |
| `DEV_MODE` | `true` | Development mode only; it does not add authentication. |
| `PB_BIND_ADDRESS` | `127.0.0.1` | Host bind address for Compose-published ports. Use `0.0.0.0` in Codespaces when required by port forwarding. |
| `MOCK_INFERENCE` | `false` | `false` uses the configured live model. Set `true` only for a deterministic simulation without real LLM reasoning. Compose and the sample `.env` default to `false`. |
| `MODEL_PROVIDER` | `ollama` | Default reasoning provider: `ollama`, `vllm` or `openai-compatible`. |
| `REASONING_API_URL` | `http://127.0.0.1:11434/v1` | Host-run OpenAI-compatible reasoning endpoint. Do not use this host address inside Docker containers. |
| `REASONING_CONTAINER_API_URL` | `http://ollama:11434/v1` | Compose-only override passed to API, worker and model bootstrap; use Docker DNS here. |
| `REASONING_MODEL` | `qwen2.5:3b` | Default model name pulled by `ollama-init` and used when an agent does not override it. |
| `VLLM_API_KEY` | `ollama` in sample; `local-dev-key` in bare settings | Bearer credential for an OpenAI-compatible model server. Ollama local use does not normally require a real API key. |
| `MULTIMODAL_API_URL` | `http://127.0.0.1:8002/v1` | Optional OpenAI-compatible vision endpoint. No vision server is included in this Compose stack. |
| `MULTIMODAL_MODEL` | `local-vision` | Model identifier for the optional vision endpoint. |

### Database, cache and object storage

| Variable | Default / effective value | Description |
|---|---|---|
| `DATABASE_URL` | Standalone: `sqlite:///./data/pinky_bread.db`; Compose: PostgreSQL at `postgres:5432` | SQLAlchemy connection. Compose services override this value and use the one-shot `migrate` service. |
| `AUTO_CREATE_SCHEMA` | `true` standalone; `false` in API/worker/MCP containers | Allow local schema creation. Compose runs migrations before app services start. |
| `REDIS_URL` | Standalone: `redis://localhost:6379/0`; Compose: `redis://valkey:6379/0` | Valkey/Redis-compatible notifications and worker wake-ups. PostgreSQL remains the durable job source of truth. |
| `STORAGE_BACKEND` | `local` standalone; `s3` in Compose | Select local filesystem or S3-compatible object storage. |
| `S3_ENDPOINT_URL` | Standalone: `http://localhost:8333`; Compose: `http://seaweedfs:8333` | S3-compatible object storage endpoint. |
| `S3_REGION` | `us-east-1` | S3 signing region. |
| `S3_BUCKET` | `pinky-bread` | Bucket for workflow and company artifacts. |
| `S3_ACCESS_KEY` | Development sample credential | S3 access key. Replace before shared deployment. |
| `S3_SECRET_KEY` | Development sample credential | S3 secret key. Replace before shared deployment. |
| `UPLOAD_DIR` | Standalone: `./data/uploads`; Compose: `/opt/pinky-bread/data/uploads` | Local upload/artifact directory. |
| `MAX_UPLOAD_MB` | `12` | Maximum artifact upload size in MB. |
| `AGENT_CONFIG_DIR` | Standalone: `./config/agents`; Compose: `/opt/pinky-bread/config/agents` | Directory containing YAML agent manifests. |

### Durable worker and LangGraph

| Variable | Default | Description |
|---|---:|---|
| `WORKER_POLL_SECONDS` | `1.5` | Worker polling interval for durable jobs. |
| `WORKER_LEASE_SECONDS` | `120` | Duration of an active worker lease. |
| `WORKER_HEARTBEAT_SECONDS` | `20` | Worker lease heartbeat interval. |
| `WORKER_MAX_ATTEMPTS` | `5` | Maximum job execution attempts. |
| `LANGGRAPH_STRICT_MSGPACK` | `true` | Enable strict MsgPack serialization for LangGraph checkpoints. |

### MCP server and identity

| Variable | Default / effective value | Description |
|---|---|---|
| `MCP_ENABLED` | `false` standalone; forced `true` for Compose API/worker | Enable the model-to-MCP client integration. The Compose stack starts and enables the MCP service automatically. |
| `MCP_SERVER_URL` | Standalone: `http://127.0.0.1:8060/mcp`; Compose: `http://mcp:8090/mcp` | MCP Streamable HTTP endpoint used by the client. |
| `MCP_HOST` | `127.0.0.1` in sample host mode; `0.0.0.0` in Compose | Interface on which the MCP server listens. |
| `MCP_PORT` | `8060` host mode; `8090` inside Compose | MCP listener port. Compose maps host port `8060` to container port `8090`. |
| `MCP_API_TOKEN` | `replace-with-a-long-random-workforce-token` in sample | Workforce bearer token with read and enqueue scopes. Use a long random secret. |
| `MCP_READ_TOKEN` | `replace-with-a-different-read-only-token` in sample | Separate read-only bearer token. Use a different long random secret. |
| `MCP_RESOURCE_URL` | Host: `http://127.0.0.1:8060/mcp`; Compose: `http://mcp:8090/mcp` | Protected MCP resource audience URL. |
| `MCP_ISSUER_URL` | Host: `http://127.0.0.1:8888/issuer`; Compose: `http://pinky-bread-api:8080/issuer` | Issuer metadata URL used by the current development verifier. It is not a Keycloak/OIDC token issuer. |
| `MCP_MAX_TOOL_ROUNDS` | `4` | Maximum model/MCP tool-calling rounds per request. |

Compose has internal development defaults for PostgreSQL credentials and SeaweedFS credentials in `docker-compose.yml`. They are not production secrets. Replace or externalize them before any shared deployment. The static MCP bearer verifier is also development-only; use OIDC/JWT validation before exposing it.

Do not commit `.env`, real API keys, passwords, access tokens, certificates or private model credentials.

## Sign in to Pinky Bread

When authentication is enabled, opening the application root (`/`) redirects unauthenticated visitors to a dedicated `/login` page. After a successful sign-in, the browser returns to the workspace. For local development, the default credentials are:

- Username: `admin`
- Password: `admin`

These credentials are deliberately restricted to `APP_ENV=development` or the Compose `APP_ENV=docker` environment and are **not enabled in production**. Change them in your local `.env` file before exposing the workspace to anyone else:

```dotenv
AUTH_ENABLED=true
DEV_AUTH_ENABLED=true
DEV_ADMIN_USERNAME=admin
DEV_ADMIN_PASSWORD=use-a-unique-local-password
SESSION_SECRET=replace-with-a-random-secret-at-least-32-characters
```

The workspace is not sent to the browser until the visitor has an authenticated session. The API and company graph endpoints also require a signed, HTTP-only browser session cookie. Sessions expire after 12 hours; static assets required by the login page remain accessible.

### Enable Google sign-in

1. In Google Cloud Console, create an OAuth 2.0 Client ID with application type **Web application**.
2. Add the exact callback URL to **Authorized redirect URIs**:
   - Local: `http://localhost:8888/auth/google/callback`
   - Codespaces: `https://YOUR-CODESPACE-8888.app.github.dev/auth/google/callback` (use the actual forwarded hostname shown by Codespaces).
3. Put the client credentials in `.env`:

```dotenv
GOOGLE_CLIENT_ID=your-google-oauth-client-id
GOOGLE_CLIENT_SECRET=your-google-oauth-client-secret
GOOGLE_REDIRECT_URI=https://YOUR-HOST/auth/google/callback
```

4. Recreate the API service:

```bash
docker compose up -d --build api
```

The Google callback validates OAuth state and requires a verified Google email address. Google sign-in is shown automatically when both credentials are configured. The current implementation authenticates a Google identity but does not yet provide organization-domain allow-lists, user provisioning, role-based authorization or tenant membership enforcement; configure those before a multi-user or production deployment.

**Important:** `admin:admin` and the sample session secret are development conveniences only. Do not use them on a public or production deployment. Set a unique password and random session secret, and disable `DEV_AUTH_ENABLED` outside local development.

## Configure commercial LLM providers

Pinky Bread supports per-agent selection between local and hosted models. Open the **Model Providers** page to check credential readiness, then choose the provider when creating or editing an AI employee.

Available providers:

- **OpenAI API** — set `OPENAI_API_KEY`; the default API endpoint is `https://api.openai.com/v1`.
- **Google Gemini API** — set `GEMINI_API_KEY`; Pinky Bread uses Google's OpenAI-compatible Chat Completions endpoint, `https://generativelanguage.googleapis.com/v1beta/openai`.
- **Ollama** — local model runtime included in Docker Compose.
- **vLLM** and **OpenAI-compatible gateway** — self-hosted or hosted inference endpoints.

Put keys in the project-root `.env` file. Do not add keys to agent profiles or commit them to Git:

```dotenv
OPENAI_API_KEY=your-openai-api-key
GEMINI_API_KEY=your-gemini-api-key
# Optional for custom OpenAI-compatible services:
OPENAI_COMPATIBLE_API_KEY=your-gateway-api-key
```

Then rebuild/recreate the API and worker so both runtime paths receive the environment variables:

```bash
docker compose up --build -d
docker compose ps
```

In an agent's **LLM provider** settings, select OpenAI or Gemini and enter a model identifier enabled for your provider account (for example, `gpt-4.1-mini` or `gemini-4-hydrogen`). Leave the endpoint blank to use the provider default, or supply a compatible endpoint override. Each agent stores only its provider, model ID and optional endpoint; the server retrieves the corresponding API key from its environment. Provider status reports whether a key is configured but never returns the secret itself.

The selected model is used for agent chat, MCP-assisted tool calls, goal planning and assigned-work execution. Gemini's OpenAI compatibility supports Chat Completions and function calling, but provider-specific capabilities are not necessarily identical to OpenAI's. Check your chosen model's API feature support before relying on advanced options. Hosted inference sends prompts and relevant company context to the provider and may incur usage charges. Review the provider's privacy, data-retention and billing settings before using sensitive company data.

## Connect the local model to MCP

The Compose stack starts the MCP v2 Streamable HTTP server automatically and enables the model-to-MCP client in the API and worker. The client discovers tools dynamically and applies per-agent role allow-lists. Company, tenant and agent identities are injected by the runtime rather than selected by the model.

Host-side integrations can reach the endpoint at `http://127.0.0.1:8060/mcp`. Inside Compose, use `http://mcp:8090/mcp`. The host port is private by default; do not expose it to untrusted networks.

Before using MCP beyond a local single-user experiment, replace `MCP_API_TOKEN` and `MCP_READ_TOKEN` in `.env` with separate long random values. The current static bearer verifier is for private development only; it is not Keycloak/OIDC, does not issue production JWTs and does not establish tenant authorization. Review [the durable runtime guide](docs/DURABLE_WORKFORCE_RUNTIME_2.0.md) before extending MCP access.

Create at least one agent with **Coordinator** authority before planning goals. From the Company Graph workspace, **Enable planning loop** lets the coordinator create plans on its schedule. **Enable auto-execution** requires explicit founder confirmation and lets the worker execute ready work. The default is disabled. Stop coordination at any time with **Pause coordination**.

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
│   ├── workforce.py      # User-defined coordinator, agent delegation, task execution, meetings and KPIs
│   ├── durable_runtime.py # PostgreSQL jobs, LangGraph checkpoints, worker leases and coordination
│   ├── agent_messaging.py # Company-scoped A2A conversations, message history and SSE stream
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
│   ├── releases/          # Versioned release notes
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
├── frontend/             # React 18 + TypeScript + Vite A2A collaboration app
│   ├── src/App.tsx
│   ├── src/styles.css
│   └── package.json
├── web/
│   ├── a2a/               # Vite output, generated during build
│   ├── app.js            # Dashboard behavior
│   ├── index.html        # Dashboard markup
│   └── styles.css        # Dashboard styling
├── .env.example          # Sample local environment settings
├── CHANGELOG.md          # Version history
├── .github/workflows/    # CI and release publishing
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
- **Workflow durability:** LangGraph + PostgreSQL checkpoints, lease recovery and bounded retries are implemented in Alpha 3/4. Add budget enforcement, richer concurrency controls, prompt/model rollback and backup/restore drills.
- **Audit integrity:** add WORM or independently protected storage, signed records, external anchoring, controlled access, and audit-chain verification tooling. Hash-linked database rows alone are not immutable.
- **Network security:** enforce egress control, ingress restrictions, mTLS, DNS policy, registry controls and host firewall rules outside this application. A Compose `internal` network is only one deployment control.
- **Secrets and supply chain:** use a secrets manager, trusted internal registries, image scanning, dependency pinning/SBOM, vulnerability scanning and signed artifacts.
- **Observability and resilience:** add OpenTelemetry traces/metrics/logs, alerting, runbooks, load testing, backup/restore and disaster recovery validation.
- **Document safety:** add upload scanning, content validation, storage encryption, retention and size/format limits appropriate to the target environment.

No regulatory certification, security assurance, production air-gap verification, or immutable-audit claim is made by this repository.

## Roadmap

See [the Alpha 2 workforce runtime guide](docs/WORKFORCE_RUNTIME_2.0.md) for the goal-to-result workflow and [Alpha 3 durable runtime guide](docs/DURABLE_WORKFORCE_RUNTIME_2.0.md) for checkpoints, worker recovery, coordination, MCP v2 and local models. Remaining roadmap increments:

1. **Workforce quality:** richer coordination, cancellation semantics, budget enforcement, agent evaluation and repeatable execution policies.
2. **Production MCP identity:** OIDC/JWT validation, authenticated tool identities, per-agent grants and tool-level policy checks.
3. **Approval security:** authenticated approvers, role/tenant checks, separation of duties and replay protection.
4. **Multimodal processing:** local OCR for scanned PDFs, image validation, vision-model integration tests and safer artifact lifecycle controls.
5. **Privacy and governance:** local NER/Presidio, secure token vault, prompt/model manifest versioning, audit export and retention policy.
6. **Platform operations:** OIDC, mTLS, OpenTelemetry, Valkey-backed coordination, policy enforcement, deployment hardening and security/load testing.

## Troubleshooting

### Local API startup and PostgreSQL connection refused

The sample `.env.example` uses SQLite for standalone API-only development. For the recommended full stack, use Docker Compose:

```bash
docker compose up --build -d
```

Compose runs a one-shot `migrate` service after PostgreSQL is healthy. The API,
worker and MCP services wait for it to complete and do not race to create the
schema. Do not run the API with a PostgreSQL URL unless PostgreSQL is reachable.

### `ModuleNotFoundError` when starting the API

Confirm the virtual environment is activated and install dependencies again:

```bash
python -m pip install -r requirements.txt
```

### Port 8888 is already in use

Choose another port, for example:

```bash
uvicorn app.main:app --reload --port 8889
```

### The dashboard shows the API as offline

Check that the server process is still running and that the browser is using the same host/port displayed in the terminal. Inspect `/api/healthz` for the service response.

### AI chat says `MOCK_INFERENCE=true`

An existing `.env` can override the sample file. Set `MOCK_INFERENCE=false`, then recreate the API, worker and model bootstrap with `docker compose up --build -d`. Verify with `docker compose exec api printenv MOCK_INFERENCE` and `docker compose exec worker printenv MOCK_INFERENCE`. Do not simply edit `.env.example`; Compose reads `.env`.

### Docker cannot resolve the model or MCP hostname

Inside Compose, use `http://ollama:11434/v1` and `http://mcp:8090/mcp`, not `localhost` or `127.0.0.1`. Check `docker compose ps`, `docker compose logs ollama ollama-init api worker mcp`, and the `REASONING_CONTAINER_API_URL` setting. From the host, use the published ports such as `127.0.0.1:11434` and `127.0.0.1:8060`.

### Agent reload reports validation errors

Review the reported YAML filename and schema error. Ensure each manifest includes the required sections and valid field types. A failed reload leaves the active last-known-good registry unchanged.

---

## License

This repository includes the Apache License, Version 2.0 in [`LICENSE`](LICENSE). Review the full license text for the permissions, conditions, limitations, and attribution requirements that apply to this project.
