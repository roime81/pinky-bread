# Pinky Bread 3.0 — Future Pipeline

**Status:** Future pipeline / research and architecture backlog  
**Dependency:** Pinky Bread 2.0 release gates and production-readiness review

Pinky Bread 3.0 is deliberately deferred while Pinky Bread 2.0 completes its company identity, workforce reliability, knowledge, governance and operational foundations. This document records candidate technologies and adoption criteria; it does not authorize adding them to the 2.0 runtime.

## 3.0 product ambition

Evolve Pinky Bread from a governed AI Company Operating System into an extensible AI-native organisation platform with richer model infrastructure, advanced LLM observability and evaluation, adaptive agent optimisation, and generative user experiences.

The company graph, business records, identity, policies and durable job contracts should remain Pinky Bread-owned. Frameworks remain replaceable implementation choices.

## Candidate technology pipeline

| Capability | Candidate | Intended value | Adoption decision |
|---|---|---|---|
| Model gateway and routing | LiteLLM | Unified model API, provider routing, fallbacks, rate limits, virtual keys and usage tracking | Evaluate after 2.0 model budgets and provider adapters are stable |
| LLM observability | Langfuse | Traces, generations, prompt versions, datasets and evaluations | Evaluate against the 2.0 OpenTelemetry baseline; avoid duplicate telemetry silos |
| Prompt/agent optimisation | DSPy | Data-driven prompt/program optimisation and repeatable evaluation | Adopt only with quality datasets, acceptance thresholds and human-reviewed promotion |
| Generative UI | CopilotKit | React-to-agent state integration, streamed actions, human-in-the-loop and dynamic UI | Evaluate after the 2.0 React workspace and API contracts are stable |
| Agent runtime | AgentScope | Runtime isolation, messaging and specialised agent execution patterns | Benchmark against the LangGraph workforce runtime and MCP architecture |
| Agent framework | CrewAI | Role/task/team abstractions and alternative multi-agent workflow orchestration | Benchmark only; do not run a second default orchestrator |
| Agent runtime | Agno | AgentOS, model/tool integrations and agent deployment capabilities | Benchmark against existing workforce services and durable job contracts |
| Visual agent automation | AutoGPT-inspired patterns | Visual workflow composition and reusable agent blocks | Borrow UX patterns or integrate selectively; do not replace the company graph |

## Proposed 3.0 architecture direction

- **Pinky Bread control plane:** company graph, user identity, memberships, governance, durable job contracts and business APIs remain platform-owned.
- **Model access plane:** optional LiteLLM gateway becomes a unified route to Ollama, vLLM, hosted commercial APIs and future model providers.
- **LLM observability plane:** Langfuse may provide model/prompt-level analysis while OpenTelemetry remains the cross-platform distributed tracing standard.
- **Optimisation plane:** DSPy experiments run against versioned evaluation datasets; improved prompts or programs are promoted only through a reviewed release process.
- **Experience plane:** CopilotKit may power generative React components and contextual agent interactions without owning business state.
- **Agent runtime plane:** LangGraph remains the default until objective benchmarks demonstrate a material advantage from another runtime. Alternative frameworks can be isolated behind adapter interfaces.
- **Integration plane:** MCP and authenticated service APIs remain the contract for tools and external systems.

## Adoption gates

A candidate must satisfy all relevant criteria before inclusion:

1. Demonstrate a clear capability gap that the 2.0 stack cannot address economically.
2. Preserve company identity, membership, permissions and audit context across every request.
3. Support durable execution or integrate with Pinky Bread's existing durable job/checkpoint contract.
4. Provide observable failure, retry, timeout and cancellation behavior.
5. Avoid duplicate sources of truth for company state, memory, prompts, users or business events.
6. Support local/self-hosted operation where required and document outbound data flows for hosted services.
7. Pass integration, security, load and recovery tests in Docker Compose.
8. Show measurable improvement in agent quality, latency, cost, developer productivity or founder experience.
9. Have a supported upgrade, rollback and exit path.

## Research and delivery sequence after 2.0

### 3.0.0 — AI infrastructure evaluation
- Benchmark LiteLLM against the existing provider adapter.
- Define a common model invocation contract, usage schema, timeout/fallback policy and secrets integration.
- Compare Langfuse with OpenTelemetry-based tracing, Prometheus and existing event records.
- Select one operational source of truth for each telemetry concern.

### 3.0.1 — Agent quality and optimisation
- Establish golden datasets for planning, task execution, A2A collaboration, meetings and retrieval.
- Evaluate DSPy against the current prompt/version workflow.
- Add offline evaluation, regression thresholds and reviewed promotion/rollback.

### 3.0.2 — Generative workspace
- Prototype CopilotKit with the existing React workspace.
- Support streamed agent state, contextual UI, approvals and interactive deliverables.
- Retain existing API and graph contracts; avoid a UI rewrite unless the prototype proves value.

### 3.0.3 — Runtime comparison
- Benchmark LangGraph against selected CrewAI, Agno and AgentScope use cases.
- Compare durability, multi-agent communication, MCP interoperability, observability, latency, cost, isolation and operational complexity.
- Keep LangGraph unless an alternative provides measurable benefits without weakening recovery and governance.

### 3.0.4 — Visual workflow composition
- Evaluate AutoGPT-inspired block-based workflow design.
- Compile visual flows into versioned, validated Pinky Bread job definitions.
- Keep execution policies, permissions, approvals and durable state in the Pinky Bread control plane.

## Non-goals

- No wholesale rewrite of the 2.0 codebase.
- No multiple competing orchestration engines in the default runtime.
- No framework-owned company data or separate tenant identity store.
- No automatic prompt or agent updates directly into production.
- No external tool side effects without the 2.0 approval, identity and audit controls.
- No hosted dependency that makes local operation impossible without an explicit product decision.

## Release principle

Pinky Bread 3.0 should extend a proven Pinky Bread 2.0 operating system. It must not be used to defer the foundational identity, security, durability, knowledge and operational work required for 2.0.
