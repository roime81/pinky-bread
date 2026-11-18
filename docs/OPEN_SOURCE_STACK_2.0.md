# Pinky Bread 2.0 — Open-Source Stack

The design goal is self-hosted operation without mandatory proprietary SaaS dependencies. Components are chosen for clear responsibilities and replaceable interfaces.

## Selected stack

| Layer | Component | Responsibility | Current status |
|---|---|---|---|
| Application API | Python, FastAPI, Pydantic | HTTP API and request validation | Implemented |
| Persistence | PostgreSQL 16, SQLAlchemy | Company graph, workflows, event history | Implemented |
| Vector extension | pgvector | Semantic memory and document retrieval | Extension enabled; vector pipeline pending |
| Live events | Valkey 9.1.3 | Pub/Sub notifications for the living graph | Implemented |
| Object storage | SeaweedFS 4.53 S3 API | Uploaded documents and workflow artifacts | Compose and storage adapter implemented |
| Local LLM | vLLM-compatible API | Local reasoning and vision inference | Existing adapter; inference server/model deployed separately |
| Workflow orchestration | LangGraph | Durable multi-agent state graph and checkpoints | Planned |
| Tool protocol | Official MCP Python SDK | Standard tool/resource/prompt integration | Planned; current tool gateway is a local demo adapter |
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

The Compose profile pins Valkey 9.1.3 and SeaweedFS 4.53 based on upstream stable releases available on 18 November 2026. The Compose profile uses:

- FastAPI application container
- PostgreSQL 16 pgvector image
- Valkey with append-only persistence enabled
- SeaweedFS with S3 gateway enabled
- Persistent Docker volumes for database, cache and objects

The Compose network is internal to the Docker deployment. It is not a complete air-gap or security boundary by itself. Host firewalling, ingress, secret management, TLS and image supply-chain controls remain deployment responsibilities.

## Storage contract

Pinky Bread code uses a storage adapter:

- `STORAGE_BACKEND=local`: filesystem storage under the configured upload directory for lightweight development.
- `STORAGE_BACKEND=s3`: S3-compatible storage using `S3_ENDPOINT_URL`, bucket and credentials.

Workflow state persists artifact ID, object key, storage URI, content type, file size and SHA-256 checksum. The file bytes are not written into graph JSON or relational text columns.

## Open-source-only operating mode

The target self-hosted mode uses a local vLLM-compatible endpoint and open-source runtime components. A model is not bundled or downloaded automatically. The current Compose file retains mock inference by default so the application can start without GPU capacity; configure an internal reasoning and vision endpoint to run actual inference.

Optional commercial model APIs may be introduced as adapters, but the core company graph, persistence, files, event delivery, orchestration and tools must continue to function without them.
