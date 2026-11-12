# Pinky Bread architecture

## Runtime layout

```text
Browser operations console
          |
          v
FastAPI REST API ---- YAML Agent Registry
          |                    |
          v                    v
Custom Workflow Engine <--- Validated Agent Manifests
          |
          +---- LocalInference ---- OpenAI-compatible vLLM reasoning endpoint
          |                         `- OpenAI-compatible local VLM endpoint for images
          |
          +---- MCP-style Gateway ---- SIMULATED refund tool (approval-gated)
          |
          +---- SQLAlchemy Persistence ---- SQLite (local) / PostgreSQL (Compose)
          |
          `---- Local Artifact Store ---- PDF, PNG, JPG files + metadata
```

## Workflow state transitions

```text
START -> ROUTER -> SPECIALIST AGENT
                    |       |
                    |       +--> END -> COMPLETED
                    |
                    +--> NEXT AGENT -> REFUND PROPOSAL
                                           |
                                           v
                                    HUMAN APPROVAL
                                      /       \
                                 APPROVE     REJECT
                                    |          |
                                    v          v
                              SIMULATED MCP  REJECTED
                                TOOL CALL
                                    |
                                    v
                                COMPLETED
```

The current engine implements the demonstration journey: aviation disruption → banking refund proposal → human approval → simulated local tool action. The dispatcher is a lightweight explicit Python state machine, not LangGraph.

## Data handling

- Prompt text and extracted PDF text are masked locally before they are sent to inference.
- The original workflow prompt remains persisted for the user-facing workflow record. This is a development choice and must be replaced by policy-based encrypted storage or minimized retention before sensitive production use.
- Text-based PDF content is extracted locally with PyMuPDF.
- Uploaded images are forwarded to the local VLM endpoint only when `MOCK_INFERENCE=false`; mock mode does not inspect image pixels.
- Artifact bytes are written to a local per-workflow directory; workflow state stores artifact metadata and path.
- Audit entries hash the input and link to the previous event hash. They are tamper-evident within the chain but not independently immutable or signed.

## Trust boundaries and explicit MVP limitations

- No authentication is implemented. Approver identity is currently a supplied identifier, not an authenticated principal.
- Tenant IDs are stored but not enforced as an authorization boundary.
- No actual MCP protocol transport is implemented; the gateway is an allow-listed adapter stub.
- Redis exists in Docker Compose but is not currently used by the engine.
- No LangGraph checkpoint engine exists yet. Workflow state is persisted in SQLAlchemy; cyclic graph execution and durable interrupt/resume behavior remain to be implemented.
- The PII scrubber uses regular expressions and is not production-grade PII/PHI detection. There is no secure token vault or rehydration mechanism.
- Audit chain is hash-linked but not WORM, signed, externally anchored or protected from a privileged database administrator.
- No OIDC, mTLS, vector search, RAG, model/prompt registry, WORM audit, or enterprise telemetry integration exists yet.
- Docker's `internal` network limits container egress; it does not replace host firewall, ingress, identity, or infrastructure security controls.
