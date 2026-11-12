from __future__ import annotations
import base64
import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import fitz
from .database import SessionLocal, WorkflowRecord, serialize_state, deserialize_state
from .inference import LocalInference
from .mcp_gateway import MCPGateway
from .privacy import scrub_text
from .registry import AgentRegistry
from .schemas import WorkflowInvokeRequest, ArtifactInput
from .settings import get_settings


class WorkflowNotFound(Exception):
    pass


class WorkflowConflict(Exception):
    pass


class WorkflowEngine:
    def __init__(self, registry: AgentRegistry):
        self.settings = get_settings()
        self.registry = registry
        self.inference = LocalInference()
        self.mcp = MCPGateway()

    async def invoke(self, request: WorkflowInvokeRequest) -> dict[str, Any]:
        thread_id = request.thread_id or str(uuid.uuid4())
        if self._load(thread_id):
            raise WorkflowConflict(f"Workflow {thread_id} already exists")

        artifact_records, extracted_text, runtime_images = self._persist_artifacts(thread_id, request.artifacts)
        scrubbed = scrub_text(request.prompt + ("\n\nExtracted document text:\n" + extracted_text if extracted_text else ""))
        state: dict[str, Any] = {
            "thread_id": thread_id,
            "tenant_id": request.tenant_id,
            "user_id": request.user_id,
            "prompt": request.prompt,
            "masked_prompt": scrubbed.text,
            "privacy_findings": scrubbed.findings,
            "artifacts": artifact_records,
            "active_agent": "",
            "next_job": None,
            "task_payload": {"document_text": extracted_text},
            "agent_outputs": [],
            "executed_agents": [],
            "requires_human_approval": False,
            "approval_status": None,
            "pending_action": None,
            "tool_result": None,
            "audit_trail": [],
            "final_response": None,
            "status": "RUNNING",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        self._audit(state, "router", "", "ROUTING", scrubbed.text, "Workflow accepted")

        first_agent = self._route(request.target_domain, scrubbed.text)
        state["active_agent"] = first_agent
        state["next_job"] = first_agent
        self._audit(state, "router", first_agent, "ROUTING", scrubbed.text, f"Selected {first_agent}")

        steps = 0
        while state["next_job"] and state["next_job"] != "END" and steps < 8:
            steps += 1
            agent_id = state["next_job"]
            if not self.registry.has(agent_id):
                state["status"] = "FAILED"
                state["final_response"] = f"Workflow stopped: unknown agent '{agent_id}'."
                self._audit(state, "dispatcher", agent_id, "ERROR", agent_id, "Agent not registered")
                break
            state["active_agent"] = agent_id
            self._audit(state, "agent_executor", agent_id, "NODE_START", state["masked_prompt"], "Agent execution started")
            manifest = self.registry.get(agent_id)
            if agent_id == "airline_ops_agent":
                await self._run_airline_agent(state, manifest, runtime_images)
            elif agent_id == "banking_refund_agent":
                self._run_refund_agent(state, manifest)
            else:
                await self._run_general_agent(state, manifest)
            if state["requires_human_approval"]:
                state["status"] = "PENDING_APPROVAL"
                state["next_job"] = "END"
                break
            # Keep an explicit hand-off target set by the current specialist.
            # If the node did not choose a different target, terminate this MVP graph.
            if not state.get("next_job") or state["next_job"] == agent_id:
                state["next_job"] = "END"

        if state["status"] == "RUNNING":
            state["status"] = "COMPLETED"
        if state["status"] == "COMPLETED" and not state["final_response"]:
            state["final_response"] = self._consolidate(state)
        self._save(state, request.prompt)
        return self._response(state)

    async def _run_airline_agent(self, state: dict, manifest, runtime_images: list[tuple[str, bytes]]) -> None:
        text = state["masked_prompt"] + "\n" + state["task_payload"].get("document_text", "")
        result = await self.inference.complete(manifest, text, runtime_images)
        evidence = (state["prompt"] + " " + state["task_payload"].get("document_text", "")).lower()
        disruption_terms = ("cancel", "cancelled", "canceled", "disrupt", "boarding pass", "flight delay", "flight delayed")
        confirmed_signal = any(term in evidence for term in disruption_terms)
        if not self.settings.mock_inference and any(term in result.lower() for term in ("cancel", "cancelled", "canceled", "disrupted")):
            confirmed_signal = True
        state["task_payload"]["disruption_signal"] = confirmed_signal
        state["agent_outputs"].append({"agent_id": manifest.agent_metadata.agent_id, "summary": result})
        state["executed_agents"].append(manifest.agent_metadata.agent_id)
        self._audit(state, "airline_ops_agent", manifest.agent_metadata.agent_id, "LLM_INFERENCE", text, result[:600])
        if confirmed_signal:
            state["task_payload"]["operations_validation"] = "POTENTIAL_DISRUPTION_DETECTED"
            state["next_job"] = "banking_refund_agent"
            self._audit(state, "airline_ops_agent", manifest.agent_metadata.agent_id, "HANDOFF", text, "Handoff to banking_refund_agent")
        else:
            state["final_response"] = "The airline operations agent did not find enough disruption evidence to prepare a refund. Provide cancellation details or a readable document and retry."
            state["next_job"] = "END"

    def _run_refund_agent(self, state: dict, manifest) -> None:
        if not state["task_payload"].get("disruption_signal"):
            state["final_response"] = "Refund preparation stopped because disruption evidence was not detected."
            state["next_job"] = "END"
            return
        amount_match = re.search(r"\bRM\s*([0-9]+(?:\.[0-9]{1,2})?)", state["prompt"], re.I)
        amount = float(amount_match.group(1)) if amount_match else 250.00
        amount = min(max(amount, 1.0), 10000.0)
        state["task_payload"]["refund_proposal"] = {"amount": amount, "currency": "MYR", "reason": "Potential flight disruption; simulated MVP proposal"}
        state["pending_action"] = {"tool": MCPGateway.REFUND_TOOL, "amount": amount, "currency": "MYR"}
        state["requires_human_approval"] = True
        state["approval_status"] = "PENDING"
        state["executed_agents"].append(manifest.agent_metadata.agent_id)
        state["agent_outputs"].append({"agent_id": manifest.agent_metadata.agent_id, "summary": f"Prepared refund proposal for RM{amount:,.2f}. No ledger action has been executed."})
        self._audit(state, "banking_refund_agent", manifest.agent_metadata.agent_id, "HUMAN_GATE", json.dumps(state["task_payload"]["refund_proposal"]), "Refund proposal paused for human approval")
        state["final_response"] = f"A simulated refund proposal of RM{amount:,.2f} is ready. No money has been moved. Human approval is required before the demo MCP tool can run."

    async def _run_general_agent(self, state: dict, manifest) -> None:
        result = await self.inference.complete(manifest, state["masked_prompt"])
        state["agent_outputs"].append({"agent_id": manifest.agent_metadata.agent_id, "summary": result})
        state["executed_agents"].append(manifest.agent_metadata.agent_id)
        state["final_response"] = result
        self._audit(state, "general_assistant_agent", manifest.agent_metadata.agent_id, "LLM_INFERENCE", state["masked_prompt"], result[:600])

    def approve(self, thread_id: str, *, approver_id: str, decision: str, notes: str) -> dict[str, Any]:
        state = self._load(thread_id)
        if not state:
            raise WorkflowNotFound(thread_id)
        if state.get("status") != "PENDING_APPROVAL" or state.get("approval_status") != "PENDING":
            raise WorkflowConflict("Workflow is not waiting for approval")
        if decision == "REJECTED":
            state["approval_status"] = "REJECTED"
            state["requires_human_approval"] = False
            state["status"] = "REJECTED"
            state["final_response"] = "The proposed refund was rejected. No ledger action was executed."
            self._audit(state, "human_approval_gate", "", "HUMAN_GATE", notes, f"Rejected by {approver_id}")
        else:
            state["approval_status"] = "APPROVED"
            proposal = state["pending_action"] or {}
            manifest = self.registry.get("banking_refund_agent")
            try:
                result = self.mcp.execute_refund_credit(
                    allowed_tools=manifest.capabilities.allowed_mcp_tools,
                    thread_id=thread_id,
                    amount=float(proposal.get("amount", 0)),
                    currency=proposal.get("currency", "MYR"),
                    approver_id=approver_id,
                )
                state["tool_result"] = result
                state["requires_human_approval"] = False
                state["status"] = "COMPLETED"
                state["final_response"] = (
                    f"Approval recorded. The demo MCP tool returned {result['result']} for "
                    f"RM{result['amount']:,.2f}. Transaction reference: {result['transaction_id']}. "
                    "This is a simulation only; no real banking ledger was accessed."
                )
                self._audit(state, "mcp_tool_gateway", "banking_refund_agent", "TOOL_CALL", json.dumps(proposal), json.dumps(result))
                self._audit(state, "human_approval_gate", "", "HUMAN_GATE", notes, f"Approved by {approver_id}")
            except Exception as exc:
                state["status"] = "FAILED"
                state["final_response"] = f"Approved workflow failed safely: {exc}"
                self._audit(state, "mcp_tool_gateway", "banking_refund_agent", "ERROR", json.dumps(proposal), str(exc))
        self._save(state, state.get("prompt", ""))
        return self._response(state)

    def get_workflow(self, thread_id: str) -> dict[str, Any]:
        state = self._load(thread_id)
        if not state:
            raise WorkflowNotFound(thread_id)
        return self._response(state)

    def list_workflows(self) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            rows = db.query(WorkflowRecord).order_by(WorkflowRecord.created_at.desc()).limit(50).all()
            return [{"thread_id": r.thread_id, "tenant_id": r.tenant_id, "status": r.status, "prompt": r.prompt[:180], "created_at": r.created_at.isoformat() if r.created_at else None} for r in rows]

    def audit(self, thread_id: str) -> dict[str, Any]:
        state = self._load(thread_id)
        if not state:
            raise WorkflowNotFound(thread_id)
        return {"thread_id": thread_id, "audit_trail": state.get("audit_trail", [])}

    def _route(self, target_domain: str | None, prompt: str) -> str:
        if target_domain:
            domain = target_domain.lower()
            for agent in self.registry.all():
                if agent.agent_metadata.domain.lower() == domain:
                    return agent.agent_metadata.agent_id
        text = prompt.lower()
        if any(word in text for word in ("flight", "airline", "boarding pass", "cancelled", "canceled", "disruption", "refund")):
            if self.registry.has("airline_ops_agent"):
                return "airline_ops_agent"
        return "general_assistant_agent" if self.registry.has("general_assistant_agent") else self.registry.all()[0].agent_metadata.agent_id

    def _persist_artifacts(self, thread_id: str, artifacts: list[ArtifactInput]) -> tuple[list[dict], str, list[tuple[str, bytes]]]:
        records: list[dict] = []
        extracted: list[str] = []
        images: list[tuple[str, bytes]] = []
        folder = self.settings.upload_dir / thread_id
        folder.mkdir(parents=True, exist_ok=True)
        for item in artifacts:
            try:
                raw = base64.b64decode(item.base64_data, validate=True)
            except Exception as exc:
                raise ValueError(f"Invalid base64 data for {item.filename}") from exc
            if len(raw) > self.settings.max_upload_bytes:
                raise ValueError(f"{item.filename} exceeds the {self.settings.max_upload_mb} MB upload limit")
            artifact_id = re.sub(r"[^A-Za-z0-9_-]", "_", item.artifact_id or str(uuid.uuid4()))[:80]
            safe_name = Path(item.filename).name.replace("..", "_")
            path = folder / f"{artifact_id}_{safe_name}"
            path.write_bytes(raw)
            record = {"artifact_id": artifact_id, "filename": safe_name, "mime_type": item.mime_type, "size_bytes": len(raw), "stored_path": str(path)}
            records.append(record)
            if item.mime_type == "application/pdf":
                try:
                    with fitz.open(stream=raw, filetype="pdf") as pdf:
                        text = "\n".join(page.get_text() for page in pdf)
                    if text.strip():
                        extracted.append(f"[{safe_name}]\n{text[:12000]}")
                except Exception:
                    extracted.append(f"[{safe_name}] PDF text extraction was unavailable.")
            else:
                images.append((item.mime_type, raw))
        return records, "\n\n".join(extracted), images

    def _audit(self, state: dict, node_id: str, agent_id: str, action_type: str, input_value: str, output_summary: str) -> None:
        trail = state.setdefault("audit_trail", [])
        previous = trail[-1]["entry_hash"] if trail else "GENESIS"
        entry = {
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "node_id": node_id,
            "agent_id": agent_id,
            "action_type": action_type,
            "input_hash": hashlib.sha256(input_value.encode("utf-8", errors="ignore")).hexdigest(),
            "output_summary": output_summary[:1000],
            "latency_ms": 0,
            "previous_hash": previous,
        }
        canonical = json.dumps(entry, sort_keys=True, ensure_ascii=False)
        entry["entry_hash"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
        trail.append(entry)

    def _save(self, state: dict, prompt: str) -> None:
        now = datetime.now(timezone.utc)
        with SessionLocal() as db:
            row = db.get(WorkflowRecord, state["thread_id"])
            if row is None:
                row = WorkflowRecord(thread_id=state["thread_id"], tenant_id=state["tenant_id"], user_id=state["user_id"], status=state["status"], prompt=prompt, state_json=serialize_state(state), final_response=state.get("final_response"), created_at=now, updated_at=now)
                db.add(row)
            else:
                row.status = state["status"]
                row.state_json = serialize_state(state)
                row.final_response = state.get("final_response")
                row.updated_at = now
            db.commit()

    def _load(self, thread_id: str) -> dict | None:
        with SessionLocal() as db:
            row = db.get(WorkflowRecord, thread_id)
            return deserialize_state(row.state_json) if row else None

    @staticmethod
    def _response(state: dict) -> dict[str, Any]:
        return {
            "thread_id": state["thread_id"],
            "status": state["status"],
            "final_response": state.get("final_response"),
            "executed_agents": state.get("executed_agents", []),
            "audit_trail": state.get("audit_trail", []),
            "requires_human_approval": state.get("requires_human_approval", False),
            "approval_status": state.get("approval_status"),
            "pending_action": state.get("pending_action"),
            "tool_result": state.get("tool_result"),
            "artifacts": state.get("artifacts", []),
            "privacy_findings": state.get("privacy_findings", []),
        }

    @staticmethod
    def _consolidate(state: dict) -> str:
        return "\n\n".join(item["summary"] for item in state.get("agent_outputs", [])) or "Workflow completed."
