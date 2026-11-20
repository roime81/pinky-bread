# Codex task: Pinky Bread 2.0.1 — identity and company authorization

This is the next 2.0 engineering increment. Do not implement Pinky Bread 3.0 technologies in this task.

Read `AGENTS.md`, `README.md`, `docs/ARCHITECTURE_2.0.md`, and `docs/ROADMAP_2.0.md` before changing code. Preserve the current company graph, workforce runtime, A2A, document ingestion, MCP, local inference and existing UI behavior.

## Objective

Replace caller-supplied tenant/actor values as authorization inputs with a verified authenticated principal and persisted company membership. A logged-in user must only access companies for which that user has an explicit membership and permitted role.

## Required design

1. Introduce a persistent user/principal model keyed by identity-provider issuer and subject. Store verified email and display metadata only when available.
2. Upsert the user after successful Google OAuth authentication. Keep development login available only in development/test/Compose profiles and ensure its principal is explicit and deterministic.
3. Introduce persisted company membership with a documented role set: FOUNDER/OWNER, ADMIN, DEPARTMENT_LEAD, AGENT, REVIEWER and AUDITOR/READ_ONLY. Define the permissions for each role.
4. Company creation must grant the authenticated creator the owner/founder membership. Never trust a request-body `owner_id` or `tenant_id` to establish ownership.
5. Derive the actor identity from the verified session or validated service principal. Legacy `actor_id` request fields may be accepted temporarily for schema compatibility, but must not override the principal when authentication is enabled.
6. Enforce company membership and role checks consistently on graph reads/writes, agents, chat, A2A conversations, meetings, KPI operations, jobs, coordination, event history/streams, artifacts and approvals.
7. Filter company listing by actual membership. Do not rely on UUID secrecy or UI filtering.
8. Protect artifact downloads and SSE endpoints with the same company authorization policy as normal API reads.
9. Add service-principal authentication and company/agent tool-scope checks for MCP. Do not weaken the current allow-list. Static development tokens must not be accepted in production mode.
10. Add CSRF protections for cookie-authenticated state-changing requests, login throttling, session revocation/rotation and secure cookie defaults.
11. Provide an explicit development migration/bootstrap path for existing local companies. Do not silently grant arbitrary users access to every existing company.
12. Keep an explicit single-user compatibility mode for automated tests and standalone local development only; test it separately from authenticated multi-user mode.

## Security requirements

- Authorization is enforced server-side on every route and object lookup.
- A caller cannot gain access by changing `company_id`, `tenant_id`, `actor_id`, object ID, job ID or agent ID.
- A company membership in one tenant does not grant access to another tenant.
- Read-only/auditor roles cannot mutate graph, job, agent or approval state.
- Only permitted roles can add/remove members, change roles, modify company policy or approve consequential actions.
- Agent tool access is the intersection of company policy, agent grants and the current job's permissions.
- Do not log cookies, passwords, API keys, OAuth tokens or full sensitive document contents.
- Do not claim production readiness, compliance or isolation until the negative tests pass.

## Tests required

- Verified Google identity is persisted and maps to one stable principal.
- Development login is rejected when disabled or outside permitted environments.
- Company creator receives owner membership.
- User A cannot read, mutate, download, stream or enqueue work in User B's company.
- Cross-company and cross-tenant IDs fail consistently for graph, agent, document, job, A2A, meeting, KPI and event APIs.
- Read-only membership cannot mutate data or approve work.
- Role changes and membership revocation take effect immediately.
- MCP service identity cannot exceed its allowed company and tool grants.
- CSRF, session expiry/revocation and login throttling behaviors are tested.
- Existing single-user tests and all current regression tests continue to pass.

## Delivery

- Implement schema migration/backfill behavior with safe failure modes.
- Update API schemas and UI handling without breaking the current login and company graph workflow.
- Update README and architecture documentation with verified behavior and remaining limitations.
- Add tests before marking an item complete.
- Run the full Python test suite, frontend build, JavaScript checks, Compose validation and relevant security tests in CI.
- Report what passed, what remains incomplete and any migration step the founder must perform.

## Constraints

- Do not introduce LiteLLM, Langfuse, DSPy, CopilotKit, CrewAI, Agno, AgentScope or AutoGPT dependencies. They are reserved for the 3.0 pipeline.
- Keep LangGraph as the only default workflow orchestrator.
- Keep PostgreSQL authoritative; Valkey is not a durable source of truth.
- Do not delete or recreate persistent Docker volumes.
- Do not connect the simulated refund/ledger example to any real financial service.
