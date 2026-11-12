# Pinky Bread

**Local-first multimodal multi-agent workflow platform**

Pinky Bread is an early-stage enterprise AI platform prototype for defining specialist AI agents, routing work between them, processing document and image artifacts, and placing sensitive downstream actions behind a human approval step. It is designed to run locally and can be configured to use OpenAI-compatible local inference endpoints such as vLLM.

The repository contains a runnable MVP: a FastAPI service, a browser-based operations console, YAML agent manifests, a deterministic workflow engine, local persistence, a simulated MCP-style tool gateway, and hash-linked audit events.

> [!IMPORTANT]
> **MVP / demonstration software.** The included refund/ledger action is simulated and never contacts a real banking system or transfers money. Mock inference is enabled by default and does not inspect image pixels. Authentication, enterprise RBAC, tenant isolation, production MCP transport, LangGraph checkpoints, production-grade PII detection, and independently immutable audit storage are not implemented. Do not use this build for production, regulated decisions, or real financial/clinical operations.

---

## Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Technology stack](#technology-stack)
- [Requirements](#requirements)
- [Install and run locally](#install-and-run-locally)
- [Run with Docker Compose](#run-with-docker-compose)
- [Configure local vLLM inference](#configure-local-vllm-inference)
- [Try the demo workflow](#try-the-demo-workflow)
- [API reference](#api-reference)
- [Configure specialist agents](#configure-specialist-agents)
- [Run tests](#run-tests)
- [Project structure](#project-structure)
- [Security and operational boundaries](#security-and-operational-boundaries)
- [Roadmap](#roadmap)
- [Troubleshooting](#troubleshooting)

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
| Web operations console | Overview, workflow submission, approval panel, recent runs, agent registry, audit view | Single-user demo UI; no login |
| Declarative agent registry | YAML manifests, Pydantic validation, reload endpoint | Registry reload is local configuration, not a governed deployment pipeline |
| Deterministic routing | Router plus explicit specialist hand-off logic | Lightweight Python state machine, not LangGraph |
| Local LLM integration | OpenAI-compatible chat completions adapter | Endpoint compatibility depends on the selected model/server |
| Mock inference | GPU-free deterministic development response | Does not understand or OCR image contents |
| Multimodal artifact intake | PNG/JPEG/PDF uploads, artifact persistence, PDF text extraction, image forwarding to configured vision endpoint | Scanned PDF OCR is not included; mock mode does not inspect images |
| Human-in-the-loop | Pending approval state, approve/reject API, approver ID and notes in audit | Approver ID is supplied by the caller; not authenticated |
| Tool access control | Agent manifest allow-list checked before simulated refund tool execution | Local MCP-style adapter only; no MCP protocol transport |
| Audit trail | SHA-256 input hashes and previous-event hash links | Tamper-evident linkage, not WORM/immutable storage or signed audit |
| Persistence | SQLAlchemy workflow state stored in SQLite or PostgreSQL | No LangGraph checkpointing or migration framework |
| Container deployment | Dockerfile and Compose with PostgreSQL and Redis | Redis is provisioned but not used by the workflow engine |

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
| Workflow orchestration | Custom Python state machine | Deterministic routing, specialist hand-offs and approval control |
| Model adapter | HTTPX, OpenAI-compatible chat completions contract | Calls local reasoning or vision model endpoints |
| Inference server (optional) | vLLM-compatible endpoint | Local model serving; deployment managed separately |
| Persistence | SQLAlchemy 2, SQLite / PostgreSQL | Workflow state and audit event persistence |
| Vector extension image | pgvector PostgreSQL image | Available in Docker stack; vector retrieval is not yet implemented |
| Cache/event service | Redis 7.2 | Provisioned in Docker stack; not yet wired into the application |
| PDF processing | PyMuPDF | Text extraction from text-based PDFs |
| Frontend | HTML, CSS, vanilla JavaScript | Browser-based console without a frontend build toolchain |
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
- Sufficient memory and disk for the API, PostgreSQL and Redis containers

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

The default configuration uses SQLite and mock inference. PostgreSQL, Redis and a GPU are not needed for this first local run.

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

# Stop containers and preserve named volumes
docker compose down

# Stop containers and remove database/cache volumes (destructive)
docker compose down --volumes
```

The Compose stack contains:

- `api`: Pinky Bread FastAPI application
- `postgres`: PostgreSQL 16 using the pgvector image
- `redis`: Redis 7.2 with append-only persistence enabled

The Compose network is configured as `internal: true`, which restricts container egress. **This is not proof of a fully air-gapped deployment.** Image pulls and package installation generally happen before deployment; host firewall rules, ingress, routing, DNS, secrets, and infrastructure controls must be reviewed independently. Redis is currently provisioned but not connected to the application workflow.

The Compose database password is a development-only value. Replace it with managed secrets before any shared or non-development deployment.

## Configure local vLLM inference

Mock mode is enabled by default. To use a local OpenAI-compatible endpoint, edit `.env`:

```dotenv
MOCK_INFERENCE=false
REASONING_API_URL=http://127.0.0.1:8001/v1
REASONING_MODEL=your-reasoning-model
MULTIMODAL_API_URL=http://127.0.0.1:8002/v1
MULTIMODAL_MODEL=your-vision-model
VLLM_API_KEY=local-development-key
```

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

The service publishes an interactive OpenAPI document at `/docs` when running.

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
| `REDIS_URL` | `redis://localhost:6379/0` | Redis URL placeholder; Redis is not yet used by the workflow engine |
| `AGENT_CONFIG_DIR` | `./config/agents` | Directory containing YAML agent manifests |
| `UPLOAD_DIR` | `./data/uploads` | Local artifact storage directory |
| `MAX_UPLOAD_MB` | `12` | Maximum size per artifact |
| `REASONING_API_URL` | `http://localhost:8001/v1` | OpenAI-compatible local reasoning endpoint base URL |
| `REASONING_MODEL` | `local-reasoner` | Default reasoning model setting; agent manifest `model_name` is used for reasoning calls |
| `MULTIMODAL_API_URL` | `http://localhost:8002/v1` | OpenAI-compatible local vision endpoint base URL |
| `MULTIMODAL_MODEL` | `local-vision` | Vision model identifier |
| `VLLM_API_KEY` | `local-dev-key` | Bearer token passed to local inference endpoint |

Do not commit a real `.env` file, API key, password, certificate, or private model credential.

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

The existing test suite covers agent listing, the aviation-to-banking hand-off, the pending-approval flow, simulated tool execution after approval, rejection without tool execution, general-agent completion, and basic NRIC/email masking.

## Project structure

```text
pinky-bread/
├── app/
│   ├── database.py       # SQLAlchemy models and persistence helpers
│   ├── engine.py         # Workflow routing, agent execution and approval flow
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
│   └── ARCHITECTURE.md   # Architecture, flow and trust boundaries
├── tests/
│   └── test_engine.py    # API/workflow behavior tests
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
- **MCP:** implement the official MCP SDK transport and authenticated tool servers. The included gateway is an in-process simulation, not a production MCP client/server.
- **Workflow durability:** migrate the custom dispatcher to LangGraph or another durable workflow engine with checkpointing, recovery, retry and idempotency controls.
- **Audit integrity:** add WORM or independently protected storage, signed records, external anchoring, controlled access, and audit-chain verification tooling. Hash-linked database rows alone are not immutable.
- **Network security:** enforce egress control, ingress restrictions, mTLS, DNS policy, registry controls and host firewall rules outside this application. A Compose `internal` network is only one deployment control.
- **Secrets and supply chain:** use a secrets manager, trusted internal registries, image scanning, dependency pinning/SBOM, vulnerability scanning and signed artifacts.
- **Observability and resilience:** add OpenTelemetry traces/metrics/logs, alerting, runbooks, load testing, backup/restore and disaster recovery validation.
- **Document safety:** add upload scanning, content validation, storage encryption, retention and size/format limits appropriate to the target environment.

No regulatory certification, security assurance, production air-gap verification, or immutable-audit claim is made by this repository.

## Roadmap

Suggested increments:

1. **Durable orchestration:** LangGraph `StateGraph`, PostgreSQL checkpoints, restart recovery, bounded retries and idempotent workflow resume.
2. **Real MCP integration:** MCP SDK server/client transport, structured tool schemas, authenticated tool identities and tool-level policy checks.
3. **Approval security:** authenticated approvers, role/tenant checks, separation of duties and replay protection.
4. **Multimodal processing:** local OCR for scanned PDFs, image validation, vision-model integration tests and safer artifact lifecycle controls.
5. **Privacy and governance:** local NER/Presidio, secure token vault, prompt/model manifest versioning, audit export and retention policy.
6. **Platform operations:** OIDC, mTLS, OpenTelemetry, Redis eventing/queueing, policy enforcement, deployment hardening and security/load testing.

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
