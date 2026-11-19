# Pinky Bread 2.0 — Durable Workforce Runtime (Alpha 3)

## Scope

Alpha 3 moves workforce execution out of the API request lifecycle and into a durable background worker pool. The existing company graph remains the source of business identity and relationships. This increment adds a durable job record, a LangGraph state machine, PostgreSQL checkpoints, Valkey wake-up notifications, restart recovery and a standard MCP tool server/client for local model integrations.

The working path is:

`Founder / Head of Agents → FastAPI job API → PostgreSQL job row → Valkey wake-up → Worker lease → LangGraph checkpoint thread → local LLM API + role-scoped MCP tools → graph updates + object storage → PostgreSQL job result`

The system is designed to remain usable if Valkey is unavailable. A missed notification delays pickup until the next database poll; it does not lose the job.

## Services and source of truth

| Service | Responsibility | Durability boundary |
|---|---|---|
| FastAPI API | Company graph, founder commands, job submission/status, coordination policy | Submits the job row before returning 202 |
| PostgreSQL 16 + pgvector | Company graph, events, object catalogue, job queue, coordination schedule and LangGraph checkpoints | Authoritative state |
| Valkey | Workforce queue wake-up and graph event notifications | Best-effort signal only; no critical state lives only here |
| Worker | Claims a job, runs its LangGraph thread, renews its lease, stores result/failure | Can be scaled horizontally |
| MCP service | Exposes company/workforce tools over Streamable HTTP | Internal service; bearer scopes checked per tool |
| SeaweedFS S3 API | Documents, assignment outputs, meeting minutes | Bytes live in object storage; PostgreSQL owns metadata |
| Ollama (default Compose service) | Self-hosted open-weight model runtime with OpenAI-compatible API | Model weights are stored in its own persistent volume |

### PostgreSQL job state

`workforce_jobs` stores:
- Company and tenant scope, target, job kind and idempotency key
- `PENDING`, `RUNNING`, `COMPLETED`, `FAILED` or `CANCELLED` state
- Attempt count, maximum attempts, next eligible time and last error
- Worker lease owner, lease expiry, heartbeat-driven extension and cancellation request
- Result JSON, creator and lifecycle timestamps

There is a partial unique index for one active job of the same kind/target/company, plus a unique company/idempotency-key constraint. This prevents concurrent producers from creating multiple active copies of the same goal/task execution. Database uniqueness remains the final arbiter if two API replicas race.

### Worker lease and recovery model

1. The API validates the company and target, writes a durable `PENDING` job and commits it.
2. It publishes a best-effort job ID notification to Valkey.
3. A worker claims the oldest eligible row using `SELECT … FOR UPDATE SKIP LOCKED` and a conditional status update.
4. The claim sets a worker ID and lease expiry. A heartbeat extends the lease while the LangGraph graph is running.
5. Only the current worker with an unexpired lease can heartbeat, complete or fail the job. A stale worker is fenced after lease expiry or when another worker owns the row.
6. A worker periodically scans PostgreSQL for expired leases. Expired jobs are requeued if attempts remain, or marked failed/cancelled after the configured retry limit.
7. If Valkey is unavailable, a worker polls PostgreSQL at `WORKER_POLL_SECONDS`. The durable job row is never deleted because a notification was missed.

The queue uses bounded exponential retry delay (up to five minutes by default). Job attempts are bounded by `WORKER_MAX_ATTEMPTS` and capped at ten.

### LangGraph checkpoints

Every job uses its durable job ID as the LangGraph `thread_id`. The current graph is:

`load_job → execute_job → persist_result → END`

The worker uses `AsyncPostgresSaver` from `langgraph-checkpoint-postgres`, calls `setup()` for checkpoint migrations, and stores state/checkpoints in PostgreSQL. When a process restarts and a lease expires, the new worker reopens the same graph thread. The domain operations are also idempotent: goal plans are not duplicated, completed work is not repeated, assignment deliverables use deterministic object keys per work/attempt, and meeting minutes reuse the meeting's stored object and graph node.

The worker sets `LANGGRAPH_STRICT_MSGPACK=true` before loading the checkpointer. Keep strict deserialization enabled for new deployments; do not allow arbitrary checkpoint payload classes.

The graph wraps business operations but does not replace the company graph. The existing relational nodes, edges and events remain independently inspectable through the company APIs.

## Continuous Head of Agents coordination

Coordination is stored per company in `company_coordination`. It is disabled until a founder explicitly enables it.

| Mode | Behaviour |
|---|---|
| `PLAN_ONLY` | On each configured interval, queue a goal planning job for active goals that do not yet have a plan. It never starts work automatically. |
| `AUTO_EXECUTE` | Plan unplanned goals; queue execution for goals with ready/backlog/planned assignments. Failed assignments are handled by bounded job retry or remain visible for founder review. |

Intervals are clamped to 60 seconds–24 hours. The web graph provides three explicit controls:
- **Enable planning loop**
- **Enable auto-execution** (requires a browser confirmation)
- **Pause coordination**

Founder-triggered goal/work/meeting actions also enqueue durable jobs. They no longer hold the browser's API request open while a local model generates a long answer. The graph UI polls job status and supports cancellation. Cancellation is cooperative: the worker checks between assignments, meeting turns and after model responses; it does not pretend to interrupt a model server's in-flight generation.

`AUTO_EXECUTE` is a permission to run planned work, not permission to spend money or perform arbitrary external side effects. This MCP server has no payment, email, customer messaging, infrastructure or other high-impact tools.

## Local LLM model and API

Pinky Bread calls a local OpenAI-compatible `/v1/chat/completions` endpoint. The same adapter is used for Head-of-Agents planning, specialist assignments and meeting discussion. Commercial APIs are not required.

Supported self-hosted options:
- **Ollama** — default Compose service, pinned to `0.40.16`. It exposes `http://ollama:11434/v1` to containers on the private application network and `http://127.0.0.1:11434` to the host.
- **vLLM** — point `REASONING_API_URL` at a reachable OpenAI-compatible vLLM endpoint.
- **Other compatible runtimes** — any self-hosted server that honours the chat-completions contract and supports tool calls when MCP is enabled.

Compose starts Ollama automatically. Set `REASONING_MODEL` in `.env` to select a model; the one-shot `ollama-init` service pulls it into the persistent volume before API and worker startup. Start with `docker compose up --build -d`.

Set these in `.env` before starting the stack:

```dotenv
MOCK_INFERENCE=false
MODEL_PROVIDER=ollama
REASONING_API_URL=http://127.0.0.1:11434/v1
REASONING_CONTAINER_API_URL=http://ollama:11434/v1
REASONING_MODEL=<model-name>
MCP_ENABLED=true
MCP_API_TOKEN=<long-random-secret>
```

Then start/recreate the API and workers:

```bash
docker compose up -d --force-recreate api worker
```

The Compose example uses a separate egress network for the optional Ollama service so it can pull model files. The default application network remains marked internal. In an air-gapped installation, preload the model volume from an approved offline source and remove Ollama's egress network. Model licences, redistribution terms, memory requirements and hardware support vary; Pinky Bread does not bundle model weights or automatically choose a model.

The default full-stack Compose configuration uses `MOCK_INFERENCE=false` and live Ollama inference. Set `MOCK_INFERENCE=true` only when intentionally running a GPU-free simulation; no genuine model reasoning is performed in mock mode.

## MCP integration

Alpha 3 uses the official MCP Python SDK v2.x and Streamable HTTP:
- Dedicated `mcp` service runs `app.mcp_server` on container port 8090 and is published as host port 8060 for private local integration.
- The local model adapter connects with the MCP v2 `Client` and `streamable_http_client`, passing auth through its `httpx2.AsyncClient`.
- MCP tool definitions are exposed to the model only through an agent-role allow-list.
- The caller's company ID, tenant ID and agent identity are injected by the runtime; the model cannot override those trusted fields in tool arguments.
- Head of Agents can read company goals/work, queue plan jobs and queue execution only if the founder has enabled `AUTO_EXECUTE`.
- Specialist agents receive read-only company/work tools by default.
- Tools that create a job use the same PostgreSQL idempotency/active-job rules as the FastAPI API.

### Authentication limitation

The current internal MCP verifier uses two static development bearer tokens:
- `MCP_API_TOKEN`: `company:read` plus `workforce:enqueue`; used only by the Head of Agents.
- `MCP_READ_TOKEN`: `company:read` only; used by specialist agents.

This is a scoped internal-development verifier, **not a production OAuth 2.1 identity provider or Keycloak integration**. The configured issuer URL is only the resource-server metadata value for this static verifier; it does not issue or validate Keycloak-signed JWTs. Keep the service on the private network, replace both default tokens with long random secrets, and keep host port 8060 private and do not expose it to untrusted networks. Keycloak/OIDC JWT/JWKS or introspection validation, company membership claims, short-lived tokens, per-agent grants and audited tool receipts remain required before shared or internet-facing operation.

## API additions

All endpoints are under `/v2`.

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/companies/{company_id}/goals/{goal_id}/jobs` | Queue goal plan or execution job (202) |
| POST | `/companies/{company_id}/work/{work_id}/jobs` | Queue one assignment (202) |
| POST | `/companies/{company_id}/meetings/{meeting_id}/jobs` | Queue meeting facilitation (202) |
| GET | `/companies/{company_id}/jobs` | List durable jobs |
| GET | `/companies/{company_id}/jobs/{job_id}` | Read job state/result/retries |
| POST | `/companies/{company_id}/jobs/{job_id}/cancel` | Request cooperative cancellation |
| GET | `/companies/{company_id}/coordination` | Read founder coordination policy |
| PUT | `/companies/{company_id}/coordination` | Enable/pause PLAN_ONLY or AUTO_EXECUTE |

The previous synchronous API routes remain for backwards compatibility and direct development/testing. The graph workspace now uses the durable job endpoints for founder actions.

## Deployment and scaling

The Compose profile contains:
- `api`: FastAPI UI and company/workforce API
- `worker`: LangGraph background worker; may be scaled horizontally
- `mcp`: internal Streamable HTTP MCP service
- `postgres`: pgvector PostgreSQL 16 and job/checkpoint database
- `valkey`: AOF-enabled notification broker
- `seaweedfs`: S3-compatible object storage
- `ollama`: default local inference service

To scale workers:

```bash
docker compose up -d --scale worker=3
```

PostgreSQL row locks, the active-job unique index and lease fencing coordinate worker replicas. Valkey is not a correctness dependency.

## Current boundaries

- The API still accepts caller-supplied tenant and actor IDs. Company-scoped authentication/RBAC and Keycloak/OIDC are not implemented.
- Static MCP bearer tokens are for private development networks only; they are not proof of user identity.
- The worker retries jobs and recovers expired leases. A model request is not forcibly interrupted; cancellation is checked at safe boundaries.
- LangGraph checkpoints and the queue are PostgreSQL-backed, but an Alembic migration programme, backup/restore drills and disaster-recovery automation are not complete.
- Job and task idempotency is implemented for current goal/task/meeting outputs. External MCP side effects are not enabled.
- The Ollama service is a model host. The `ollama-init` bootstrap pulls the configured model automatically on first startup; model weights are persisted separately from the container image.
- pgvector remains enabled but the semantic embedding/retrieval pipeline is not yet implemented.
- Event hash links are tamper-evident, not WORM or independently immutable.
- Metrics, distributed tracing, alerting, budgets, rate limits, model/prompt version rollback and production policy enforcement remain future work.

## Validation

The CI workflow uses PostgreSQL 16 and Valkey services. It checks browser JavaScript, Compose YAML, durable job de-duplication/lease recovery, recurring coordination, PostgreSQL checkpoint persistence and restart replay, MCP v2 server/tool discovery and the existing company graph/workforce regression suite.
