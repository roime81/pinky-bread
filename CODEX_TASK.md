# Codex task: advance Pinky Bread toward enterprise-grade alpha

Read `AGENTS.md`, `README.md`, and `docs/ARCHITECTURE.md` before changing code. Work in small, testable increments and do not remove existing capabilities.

## Immediate task

Replace `WorkflowEngine`'s hand-written execution loop with a LangGraph `StateGraph` and durable PostgreSQL checkpoints while preserving the current API contract and demo behavior.

## Required behavior

1. YAML manifests remain the source of agent identity, prompts, model configuration, allowed MCP tools and workflow wiring.
2. The router chooses the initial specialist and graph edges perform deterministic hand-offs.
3. A refund proposal transitions to a persisted human-approval interrupt; the graph can resume after an authenticated approval decision.
4. A rejection terminates without calling any MCP tool.
5. Approval may execute only an allow-listed tool. The current demo tool must remain simulated.
6. Each node transition emits an audit event with actor, model version, prompt/manifest version, input hash, output summary, latency and previous-event hash.
7. Workflow resume is idempotent. Repeated approval submissions must not execute a tool twice.
8. Preserve `/v1/workflows/invoke`, `/v1/workflows/{thread_id}/approve`, `/v1/workflows/{thread_id}`, `/v1/agents`, `/v1/agents/reload` and `/v1/audit/{thread_id}` unless a backwards-compatible extension is needed.

## Tests to add

- Graph routes aviation disruption → banking refund.
- Graph persists and resumes after interrupt/restart.
- Rejection never calls the MCP tool.
- Repeated approval does not duplicate a tool call.
- Unauthorized and wrong-tenant approval fail.
- A disallowed tool URI is rejected.
- Invalid YAML reload preserves last-known-good manifests.
- Graph checkpoint and audit chain stay consistent after resume.

## Constraints

Do not claim production air-gap, compliance, privacy or immutability based only on code-level configuration. Do not connect to a live banking ledger. Do not weaken approval or tool allow-list checks to make tests pass. Update documentation to distinguish verified features from remaining gaps. Run the full test suite and report exactly what passed and what remains unimplemented.
