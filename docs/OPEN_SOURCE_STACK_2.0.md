# Pinky Bread 2.0 — Open-Source Stack

The design goal is self-hosted operation without mandatory proprietary SaaS dependencies. Components are chosen for clear responsibilities and replaceable interfaces. Alpha 3 adds durable orchestration and a standards-based MCP boundary while retaining the Alpha 1/2 company graph and storage contract.

## Selected stack

| Layer | Component | Responsibility | Current status |
|---|---|---|---|
| Application API | Python, FastAPI, Pydantic | HTTP API and request validation | Implemented |
| Persistence | PostgreSQL 16, SQLAlchemy | Company graph, workflows, event history | Implemented |
| Vector extension | pgvector | Semantic memory and document retrieval | Extension enabled; vector pipeline pending |
| Live events | Valkey 9.1.3 | Pub/Sub notifications for the living graph | Implemented |
| Object storage | SeaweedFS 4.53 S3 API | Company documents, generated deliverables, meeting minutes and workflow artifacts | Compose and adapter implemented |
| Local LLM | Ollama 0.40.16 (optional Compose profile), vLLM or another OpenAI-compatible local server | Head-of-Agents planning, specialist execution and meeting turns | Alpha 3 supports local `/v1/chat/completions`; no model weights bundled |
| Workforce planning and execution | FastAPI + company graph + local OpenAI-compatible inference | Head-of-Agents planning, specialist execution and stored deliverables | Implemented in Alpha 2 |
| Durable job queue | PostgreSQL jobs, idempotency index, leases and retry policy | Worker claims, heartbeat, fencing, cancellation and crash recovery | Implemented in Alpha 3 |
| Durable workflow orchestration | LangGraph StateGraph + AsyncPostgresSaver | Per-job checkpoint thread and restart replay | Implemented in Alpha 3 |
| Worker coordination | Valkey Pub/Sub + PostgreSQL polling | Low-latency wake-up with database-authoritative queue | Implemented in Alpha 3 |
| Tool protocol | Official MCP Python SDK v2, Streamable HTTP | Internal MCP server/client, role-based tool allow-list and identity injection | Implemented in Alpha 3; static development bearer tokens only |
| Identity | Keycloak / OIDC | Login, SSO, company membership and identity claims | Planned |
| Secrets | OpenBao | Runtime credentials, rotation and access control | Planned |
| Policy | Open Policy Agent | Approval and agent/tool authorisation policies | Planned |
| Telemetry | OpenTelemetry | Traces, metrics and logs from agents and tools | Planned |
| Metrics | Prometheus | Metrics collection and alert rules | Planned |
| Dashboards | Grafana | Operations and performance dashboards | Planned |

## Why Valkey instead of Redis

Valkey is a BSD-licensed, Redis-compatible open-source datastore. It is suitable for the existing Redis-protocol integration and avoids binding Pinky Bread to Redis licensing or product governance. The current application uses the Redis Python client protocol against Valkey; PostgreSQL remains the durable event store.

References:
- [Valkey project](https://valkey.io/)
- [Valkey GitHub repository](https://github.com/valkey-io/valkey)

## Why SeaweedFS instead of MinIO

MinIO's community repository was archived in April 2026 and is no longer maintained. Pinky Bread 2.0 therefore uses SeaweedFS as the default self-hosted S3-compatible object store. The application uses the standard S3 API through boto3 so another compatible provider can be configured without changing business logic.

References:
- [SeaweedFS project and Apache-2.0 license](https://github.com/seaweedfs/seaweedfs)
- [SeaweedFS S3 API command and credential configuration](https://github.com/seaweedfs/seaweedfs/blob/master/weed/command/s3.go)
- [MinIO repository archive status](https://github.com/minio/minio)

## Local deployment profile

The Compose profile pins Valkey 9.1.3 and SeaweedFS 4.53 based on upstream stable releases available on 18 November 2026. The default Compose profile uses:

- FastAPI application container
- Horizontally scalable workforce worker container(s)
- Internal Streamable HTTP MCP service
- PostgreSQL 16 pgvector image and LangGraph checkpoint tables
- Valkey with append-only persistence enabled
- SeaweedFS with S3 gateway enabled
- Persistent Docker volumes for database, cache and objects

The optional `local-llm` profile adds the Ollama 0.40.16 service and a persistent model volume. Set `REASONING_API_URL=http://ollama:11434/v1`, `MOCK_INFERENCE=false` and `REASONING_MODEL` to a model name, then pull the selected model separately. The image does not include model weights. Worker replicas use PostgreSQL row locks and leases; Valkey is only an acceleration layer.

The Compose network is internal to the Docker deployment. It is not a complete air-gap or security boundary by itself. Host firewalling, ingress, secret management, TLS and image supply-chain controls remain deployment responsibilities.

## Storage contract

Pinky Bread code uses a storage adapter:

- `STORAGE_BACKEND=local`: filesystem storage under the configured upload directory for lightweight development.
- `STORAGE_BACKEND=s3`: S3-compatible storage using `S3_ENDPOINT_URL`, bucket and credentials.

Workflow state persists artifact ID, object key, storage URI, content type, file size and SHA-256 checksum. The file bytes are not written into graph JSON or relational text columns.

## Open-source-only operating mode

The target self-hosted mode uses Ollama or a vLLM-compatible local endpoint and open-source runtime components. A model is not bundled or downloaded automatically. The default Compose file retains mock inference so the application can start without GPU capacity; enable the optional Ollama profile or configure an internal reasoning endpoint to run actual inference. Open-weight model licences differ; review the selected model's terms before redistribution or business use.

Optional commercial model APIs may be introduced as adapters, but the core company graph, persistence, files, event delivery, orchestration and tools must continue to function without them.
