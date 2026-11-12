# Codex instructions for Pinky Bread

You are the senior engineer responsible for this repository. Build Pinky Bread into a secure, locally hosted, enterprise multimodal multi-agent platform. Preserve the product's intended capabilities: declarative YAML agents, deterministic graph hand-offs, local-only reasoning and vision, MCP-mediated tools, durable workflow state, human approval gates, and complete auditability.

## Engineering principles

- Treat the repository's `README.md` and `docs/ARCHITECTURE.md` as the current description of implemented behavior and limitations.
- Do not describe an integration as complete unless it exists and is covered by tests.
- Keep the default development setup runnable without GPUs or external SaaS LLM APIs.
- Keep all demo financial tools simulated. Never add a live ledger integration without an explicit separate requirement and a safe test environment.
- Do not weaken authorization, tool allow-list, privacy, or approval checks to make tests pass.
- Add or update tests for every behavior change.
- Preserve backwards compatibility for existing API routes unless a documented versioned change is necessary.
- Never commit secrets, local `.env` files, model weights, runtime databases, uploads, or generated caches.

## Immediate engineering priorities

1. Replace the hand-written workflow loop with a LangGraph `StateGraph` and durable PostgreSQL checkpoints while preserving the current REST API behavior.
2. Implement authenticated approval decisions with OIDC/JWT validation, tenant authorization, separation of duties, and idempotent resume.
3. Replace the local MCP-style adapter with the official MCP SDK transport, typed tool schemas, authenticated tool identities, and per-agent allow-list enforcement. Keep the refund tool simulated.
4. Implement robust multimodal processing, including local OCR for scanned PDFs and integration tests against a local vision model endpoint.
5. Upgrade privacy masking to tested local PII/PHI detection, controlled tokenization, encrypted sensitive state, and explicit retention policies.
6. Strengthen auditability with independently protected/WORM storage, signed events, chain verification and export.
7. Add OpenTelemetry, operational dashboards, alerts, runbooks, backup/restore tests and deployment security controls.

## Required tests for workflow/orchestration work

- Graph routes aviation disruption → banking refund.
- Graph persists and resumes after interrupt/restart.
- Rejection never calls the MCP tool.
- Repeated approval does not duplicate a tool call.
- Unauthorized and wrong-tenant approval fail.
- A disallowed tool URI is rejected.
- Invalid YAML reload preserves last-known-good manifests.
- Graph checkpoint and audit chain stay consistent after resume.

## Delivery requirements

Run the full test suite. Update `README.md` and `docs/ARCHITECTURE.md` with what is implemented, what was verified, and what remains incomplete. Report exact test results and do not claim production air-gap, compliance, privacy or immutability based only on code-level configuration.
