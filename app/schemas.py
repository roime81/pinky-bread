from __future__ import annotations
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field, ConfigDict, field_validator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AgentMetadata(BaseModel):
    agent_id: str = Field(min_length=2, max_length=100, pattern=r"^[a-zA-Z0-9_-]+$")
    display_name: str
    domain: str
    version: str


class ModelConfiguration(BaseModel):
    provider: str = "local_vllm"
    endpoint: str | None = None
    model_name: str
    temperature: float = Field(default=0.1, ge=0, le=2)
    max_tokens: int = Field(default=1200, ge=64, le=32768)


class PersonaAndGuardrails(BaseModel):
    system_prompt: str
    require_human_approval_above_risk_score: float = Field(default=1.0, ge=0, le=1)


class Capabilities(BaseModel):
    allowed_mcp_tools: list[str] = Field(default_factory=list)
    rag_collections: list[str] = Field(default_factory=list)


class WorkflowWiring(BaseModel):
    can_handoff_to: list[str] = Field(default_factory=list)
    default_next_job: str = "END"


class AgentManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    agent_metadata: AgentMetadata
    model_configuration: ModelConfiguration
    persona_and_guardrails: PersonaAndGuardrails
    capabilities: Capabilities = Field(default_factory=Capabilities)
    workflow_wiring: WorkflowWiring = Field(default_factory=WorkflowWiring)


class ArtifactInput(BaseModel):
    artifact_id: str | None = None
    filename: str
    mime_type: Literal["image/png", "image/jpeg", "application/pdf"]
    base64_data: str

    @field_validator("base64_data")
    @classmethod
    def check_base64_nonempty(cls, v: str) -> str:
        if not v:
            raise ValueError("Artifact data cannot be empty")
        return v


class WorkflowInvokeRequest(BaseModel):
    thread_id: str | None = None
    tenant_id: str = "demo-tenant"
    user_id: str = "demo-user"
    prompt: str = Field(min_length=1, max_length=12000)
    target_domain: str | None = None
    artifacts: list[ArtifactInput] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    approver_id: str = Field(min_length=2, max_length=120)
    decision: Literal["APPROVED", "REJECTED"]
    notes: str = Field(default="", max_length=2000)


class WorkflowResponse(BaseModel):
    thread_id: str
    status: str
    final_response: str | None = None
    executed_agents: list[str] = Field(default_factory=list)
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    requires_human_approval: bool = False
