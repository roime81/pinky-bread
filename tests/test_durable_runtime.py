from __future__ import annotations

import asyncio
import os
import uuid

os.environ.setdefault("LANGGRAPH_STRICT_MSGPACK", "true")
from datetime import timedelta

from fastapi.testclient import TestClient

from app.database import SessionLocal, init_db
from app.durable_runtime import (
    CompanyCoordination,
    WorkforceJob,
    claim_next_job,
    complete_job,
    configure_coordination,
    enqueue_job,
    get_job,
    list_jobs,
    recover_expired_jobs,
    run_coordination_tick,
    utcnow,
)
from app.main import app


def _company_and_goal(tenant: str):
    init_db()
    with TestClient(app) as client:
        company_response = client.post("/v2/companies", json={
            "tenant_id": tenant,
            "owner_id": "founder",
            "name": f"Durable Runtime {tenant}",
            "vision": "Build a sustainable self-hosted business",
            "mission": "Deliver useful products with a virtual workforce",
        })
        assert company_response.status_code == 201, company_response.text
        company = company_response.json()
        goal_response = client.post(f"/v2/companies/{company['id']}/nodes", json={
            "tenant_id": tenant,
            "actor_id": "founder",
            "node_type": "goal",
            "name": "Prepare the first product launch",
            "description": "Create a verifiable product launch plan",
            "status": "PLANNED",
        })
        assert goal_response.status_code == 201, goal_response.text
        return company, goal_response.json()


def test_postgres_job_queue_deduplicates_claims_heartbeats_and_recovers_expired_leases():
    company, goal = _company_and_goal(f"durable-queue-{uuid.uuid4().hex[:8]}")
    tenant = company["tenant_id"]
    job = enqueue_job(
        company_id=company["id"],
        tenant_id=tenant,
        kind="goal_plan",
        target_id=goal["id"],
        actor_id="founder",
        idempotency_key=f"plan:{goal['id']}",
    )
    duplicate = enqueue_job(
        company_id=company["id"],
        tenant_id=tenant,
        kind="goal_plan",
        target_id=goal["id"],
        actor_id="founder",
        idempotency_key=f"plan:{goal['id']}",
    )
    assert duplicate["job_id"] == job["job_id"]
    assert duplicate["deduplicated"] is True

    active_duplicate = enqueue_job(
        company_id=company["id"],
        tenant_id=tenant,
        kind="goal_plan",
        target_id=goal["id"],
        actor_id="founder",
        idempotency_key="second-key-same-active-target",
    )
    assert active_duplicate["job_id"] == job["job_id"]
    assert active_duplicate["deduplicated"] is True

    claimed = claim_next_job("worker-one", lease_seconds=30)
    assert claimed is not None
    assert claimed["job_id"] == job["job_id"]
    assert claimed["status"] == "RUNNING"
    assert claimed["attempts"] == 1
    assert complete_job(job["job_id"], "not-the-owner", {"ok": True}) is False
    assert complete_job(job["job_id"], "worker-one", {"ok": True}) is True

    completed = get_job(job_id=job["job_id"], company_id=company["id"], tenant_id=tenant)
    assert completed["status"] == "COMPLETED"
    assert completed["result"] == {"ok": True}

    second = enqueue_job(
        company_id=company["id"],
        tenant_id=tenant,
        kind="goal_execution",
        target_id=goal["id"],
        actor_id="founder",
        idempotency_key="execution-after-plan",
    )
    claimed_second = claim_next_job("worker-two", lease_seconds=30)
    assert claimed_second["job_id"] == second["job_id"]

    with SessionLocal() as db:
        db.query(WorkforceJob).filter(WorkforceJob.job_id == second["job_id"]).update(
            {WorkforceJob.lease_expires_at: utcnow() - timedelta(seconds=10)},
            synchronize_session=False,
        )
        db.commit()

    assert recover_expired_jobs() == 1
    recovered = get_job(job_id=second["job_id"])
    assert recovered["status"] == "PENDING"
    assert recovered["lease_owner"] is None
    assert recovered["lease_expires_at"] is None

    reclaimed = claim_next_job("worker-three", lease_seconds=30)
    assert reclaimed["job_id"] == second["job_id"]
    assert reclaimed["attempts"] == 2
    assert complete_job(second["job_id"], "worker-three", {"ok": True}) is True


def test_founder_coordination_is_persisted_and_queues_plan_jobs():
    company, goal = _company_and_goal(f"durable-coordination-{uuid.uuid4().hex[:8]}")
    tenant = company["tenant_id"]
    policy = configure_coordination(
        company_id=company["id"],
        tenant_id=tenant,
        actor_id="founder",
        enabled=True,
        mode="PLAN_ONLY",
        interval_seconds=60,
    )
    assert policy["enabled"] is True
    assert policy["mode"] == "PLAN_ONLY"

    queued = run_coordination_tick()
    assert queued >= 1
    jobs = list_jobs(company_id=company["id"], tenant_id=tenant)
    goal_jobs = [job for job in jobs if job["kind"] == "goal_plan" and job["target_id"] == goal["id"]]
    assert len(goal_jobs) == 1
    assert goal_jobs[0]["status"] == "PENDING"

    # The due time advances durably, so another worker tick must not enqueue again.
    run_coordination_tick()
    assert len(list_jobs(company_id=company["id"], tenant_id=tenant)) == 1

    paused = configure_coordination(
        company_id=company["id"],
        tenant_id=tenant,
        actor_id="founder",
        enabled=False,
        mode="PLAN_ONLY",
        interval_seconds=60,
    )
    assert paused["enabled"] is False
    # Keep the global worker queue isolated for the following restart test.
    from app.durable_runtime import cancel_job
    cancelled = cancel_job(
        job_id=goal_jobs[0]["job_id"],
        company_id=company["id"],
        tenant_id=tenant,
    )
    assert cancelled["status"] == "CANCELLED"


def test_langgraph_checkpoint_resume_after_worker_lease_expiry_is_idempotent():
    os.environ["LANGGRAPH_STRICT_MSGPACK"] = "true"
    company, goal = _company_and_goal(f"langgraph-resume-{uuid.uuid4().hex[:8]}")
    tenant = company["tenant_id"]
    # New companies no longer receive a predefined roster. Provision the
    # coordinator and the six specialists explicitly as a founder would.
    with TestClient(app) as client:
        coordinator = client.post(f"/v2/companies/{company['id']}/agents", json={
            "tenant_id": tenant,
            "actor_id": "founder",
            "name": "Nora",
            "role": "Company coordination",
            "title": "Chief of Staff",
            "authority": "COORDINATOR",
        })
        assert coordinator.status_code == 201, coordinator.text
        for index in range(1, 7):
            specialist = client.post(f"/v2/companies/{company['id']}/agents", json={
                "tenant_id": tenant,
                "actor_id": "founder",
                "name": f"Specialist {index}",
                "role": f"Custom function {index}",
                "title": f"Specialist {index}",
            })
            assert specialist.status_code == 201, specialist.text
    queued = enqueue_job(
        company_id=company["id"],
        tenant_id=tenant,
        kind="goal_plan",
        target_id=goal["id"],
        actor_id="founder",
        idempotency_key=f"langgraph-plan:{goal['id']}",
    )
    first_claim = claim_next_job("checkpoint-worker-one", lease_seconds=30)
    assert first_claim["job_id"] == queued["job_id"]

    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
    from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
    from app.durable_runtime import build_job_graph, execute_durable_job
    strict_serde = JsonPlusSerializer(allowed_msgpack_modules=None)

    settings_url = os.environ["DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://")

    async def run_first_attempt():
        async with AsyncPostgresSaver.from_conn_string(settings_url, serde=strict_serde) as checkpointer:
            await checkpointer.setup()
            graph = build_job_graph(checkpointer, "checkpoint-worker-one")
            return await execute_durable_job(graph, first_claim)

    first_result = asyncio.run(run_first_attempt())
    assert first_result["created"] is True
    assert first_result["count"] == 6

    # Simulate a process loss after LangGraph has checkpointed its result but
    # before the queue row could be marked complete.
    with SessionLocal() as db:
        db.query(WorkforceJob).filter(WorkforceJob.job_id == queued["job_id"]).update(
            {WorkforceJob.lease_expires_at: utcnow() - timedelta(seconds=10)},
            synchronize_session=False,
        )
        db.commit()
    assert recover_expired_jobs() == 1
    second_claim = claim_next_job("checkpoint-worker-two", lease_seconds=30)
    assert second_claim["job_id"] == queued["job_id"]
    assert second_claim["attempts"] == 2

    async def run_recovered_attempt():
        async with AsyncPostgresSaver.from_conn_string(settings_url) as checkpointer:
            await checkpointer.setup()
            graph = build_job_graph(checkpointer, "checkpoint-worker-two")
            return await execute_durable_job(graph, second_claim)

    recovered_result = asyncio.run(run_recovered_attempt())
    assert recovered_result["count"] == 6
    assert recovered_result["goal_id"] == goal["id"]
    assert complete_job(queued["job_id"], "checkpoint-worker-two", recovered_result) is True

    graph_response = None
    with TestClient(app) as client:
        graph_response = client.get(
            f"/v2/companies/{company['id']}/graph?tenant_id={tenant}"
        )
    assert graph_response.status_code == 200
    graph = graph_response.json()
    work = [
        node for node in graph["nodes"]
        if node["type"] == "work" and (node.get("data") or {}).get("goal_id") == goal["id"]
    ]
    assert len(work) == 6
    assert len({(node.get("data") or {}).get("task_key") for node in work}) == 6
    final_job = get_job(job_id=queued["job_id"])
    assert final_job["status"] == "COMPLETED"
    assert final_job["attempts"] == 2


def test_official_mcp_v2_server_exposes_scoped_tools_and_client_removes_runtime_identity_fields(monkeypatch):
    from mcp import Client
    from app.mcp_client import ROLE_TOOL_ALLOWLIST, _tool_schema
    from app.mcp_server import StaticBearerVerifier, mcp
    from app.settings import get_settings

    class ExampleTool:
        input_schema = {
            "type": "object",
            "properties": {
                "company_id": {"type": "string"},
                "tenant_id": {"type": "string"},
                "actor_id": {"type": "string"},
                "goal_id": {"type": "string"},
            },
            "required": ["company_id", "tenant_id", "goal_id"],
        }

    schema = _tool_schema(ExampleTool())
    assert set(schema["properties"]) == {"goal_id"}
    assert schema["required"] == ["goal_id"]
    assert "queue_goal_execution" in ROLE_TOOL_ALLOWLIST["head_of_agents"]
    assert "queue_goal_execution" not in ROLE_TOOL_ALLOWLIST["strategy"]

    settings = get_settings()
    monkeypatch.setattr(settings, "mcp_api_token", "internal-workforce-token")
    monkeypatch.setattr(settings, "mcp_read_token", "readonly-workforce-token")
    verifier = StaticBearerVerifier()
    write_access = asyncio.run(verifier.verify_token("internal-workforce-token"))
    read_access = asyncio.run(verifier.verify_token("readonly-workforce-token"))
    denied_access = asyncio.run(verifier.verify_token("not-a-token"))
    assert write_access is not None
    assert set(write_access.scopes) == {"company:read", "workforce:enqueue"}
    assert read_access is not None
    assert read_access.scopes == ["company:read"]
    assert denied_access is None

    async def discover_tools():
        async with Client(mcp) as client:
            result = await client.list_tools()
            return {tool.name for tool in result.tools}

    names = asyncio.run(discover_tools())
    assert {
        "company_graph_snapshot",
        "list_company_goals",
        "list_goal_work",
        "get_workforce_job",
        "queue_goal_plan",
        "queue_goal_execution",
    }.issubset(names)
