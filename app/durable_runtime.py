from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, TypedDict

from sqlalchemy import Boolean, DateTime, Index, Integer, JSON, String, Text, UniqueConstraint, and_, or_
from sqlalchemy.orm import Mapped, mapped_column

from langgraph.graph import END, StateGraph

from .company_graph import get_company_graph
from .database import Base, SessionLocal
from .settings import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class WorkforceJob(Base):
    """Durable work queue row. PostgreSQL is authoritative; Valkey only signals workers."""

    __tablename__ = "workforce_jobs"
    __table_args__ = (
        Index("ix_workforce_jobs_claim", "status", "available_at", "created_at"),
        Index("ix_workforce_jobs_company", "company_id", "created_at"),
        Index("ix_workforce_jobs_lease", "status", "lease_expires_at"),
        UniqueConstraint("company_id", "idempotency_key", name="uq_workforce_job_idempotency"),
    )

    job_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    target_id: Mapped[str] = mapped_column(String(36), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(180))
    status: Mapped[str] = mapped_column(String(24), default="PENDING", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=5)
    available_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class CompanyCoordination(Base):
    """Founder-controlled recurring Head-of-Agents coordination policy."""

    __tablename__ = "company_coordination"

    company_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    mode: Mapped[str] = mapped_column(String(24), default="PLAN_ONLY")
    interval_seconds: Mapped[int] = mapped_column(Integer, default=300)
    next_run_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(String(120))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


def _job_dict(job: WorkforceJob) -> dict[str, Any]:
    return {
        "job_id": job.job_id,
        "company_id": job.company_id,
        "tenant_id": job.tenant_id,
        "kind": job.kind,
        "target_id": job.target_id,
        "idempotency_key": job.idempotency_key,
        "status": job.status,
        "payload": job.payload or {},
        "result": job.result,
        "last_error": job.last_error,
        "attempts": job.attempts,
        "max_attempts": job.max_attempts,
        "available_at": job.available_at.isoformat() if job.available_at else None,
        "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
        "cancel_requested": job.cancel_requested,
        "created_by": job.created_by,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
    }


def _notify_workers(job_id: str) -> None:
    """Best-effort wake-up. A lost notification cannot lose a committed job."""
    try:
        from redis import Redis

        client = Redis.from_url(
            get_settings().redis_url,
            decode_responses=True,
            socket_connect_timeout=0.3,
            socket_timeout=0.3,
        )
        client.publish("pinky-bread:workforce:jobs", job_id)
        client.close()
    except Exception:
        return


def enqueue_job(
    *,
    company_id: str,
    tenant_id: str,
    kind: str,
    target_id: str,
    actor_id: str,
    idempotency_key: str | None = None,
    payload: dict[str, Any] | None = None,
    max_attempts: int = 5,
) -> dict[str, Any]:
    allowed = {"goal_plan", "goal_execution", "work_execution", "meeting"}
    if kind not in allowed:
        raise ValueError(f"Unsupported workforce job kind: {kind}")
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise LookupError("Company not found")
    ids = {node["id"] for node in graph.get("nodes", [])}
    if target_id not in ids:
        raise LookupError("Job target not found in this company")
    key = (idempotency_key or f"request:{uuid.uuid4()}")[:180]
    with SessionLocal() as db:
        existing = db.query(WorkforceJob).filter(
            WorkforceJob.company_id == company_id,
            WorkforceJob.idempotency_key == key,
        ).first()
        if existing:
            return {**_job_dict(existing), "deduplicated": True}
        active = db.query(WorkforceJob).filter(
            WorkforceJob.company_id == company_id,
            WorkforceJob.tenant_id == tenant_id,
            WorkforceJob.kind == kind,
            WorkforceJob.target_id == target_id,
            WorkforceJob.status.in_(["PENDING", "RUNNING"]),
        ).order_by(WorkforceJob.created_at.desc()).first()
        if active:
            return {**_job_dict(active), "deduplicated": True}
        job = WorkforceJob(
            job_id=str(uuid.uuid4()),
            company_id=company_id,
            tenant_id=tenant_id,
            kind=kind,
            target_id=target_id,
            idempotency_key=key,
            status="PENDING",
            payload=payload or {},
            attempts=0,
            max_attempts=min(max(max_attempts, 1), 10),
            available_at=utcnow(),
            created_by=actor_id,
        )
        db.add(job)
        db.commit()
        db.refresh(job)
        result = _job_dict(job)
    _notify_workers(result["job_id"])
    return {**result, "deduplicated": False}


def get_job(*, job_id: str, company_id: str | None = None, tenant_id: str | None = None) -> dict[str, Any] | None:
    with SessionLocal() as db:
        query = db.query(WorkforceJob).filter(WorkforceJob.job_id == job_id)
        if company_id is not None:
            query = query.filter(WorkforceJob.company_id == company_id)
        if tenant_id is not None:
            query = query.filter(WorkforceJob.tenant_id == tenant_id)
        job = query.first()
        return _job_dict(job) if job else None


def list_jobs(*, company_id: str, tenant_id: str, limit: int = 100) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        jobs = (
            db.query(WorkforceJob)
            .filter(WorkforceJob.company_id == company_id, WorkforceJob.tenant_id == tenant_id)
            .order_by(WorkforceJob.created_at.desc())
            .limit(min(max(limit, 1), 250))
            .all()
        )
        return [_job_dict(job) for job in jobs]


def claim_next_job(worker_id: str, lease_seconds: int = 90) -> dict[str, Any] | None:
    now = utcnow()
    with SessionLocal() as db:
        query = (
            db.query(WorkforceJob)
            .filter(
                WorkforceJob.status == "PENDING",
                WorkforceJob.available_at <= now,
                WorkforceJob.cancel_requested.is_(False),
            )
            .order_by(WorkforceJob.created_at.asc())
            .with_for_update(skip_locked=True)
        )
        job = query.first()
        if job is None:
            return None
        # The conditional UPDATE keeps the claim safe on SQLite development
        # databases where SELECT ... FOR UPDATE is not implemented.
        claimed = db.query(WorkforceJob).filter(
            WorkforceJob.job_id == job.job_id,
            WorkforceJob.status == "PENDING",
        ).update(
            {
                WorkforceJob.status: "RUNNING",
                WorkforceJob.lease_owner: worker_id,
                WorkforceJob.lease_expires_at: now + timedelta(seconds=max(lease_seconds, 15)),
                WorkforceJob.attempts: WorkforceJob.attempts + 1,
                WorkforceJob.started_at: now,
                WorkforceJob.updated_at: now,
            },
            synchronize_session=False,
        )
        if claimed != 1:
            db.rollback()
            return None
        db.commit()
        job = db.query(WorkforceJob).filter(WorkforceJob.job_id == job.job_id).first()
        return _job_dict(job) if job else None


def heartbeat_job(job_id: str, worker_id: str, lease_seconds: int = 90) -> bool:
    now = utcnow()
    with SessionLocal() as db:
        changed = db.query(WorkforceJob).filter(
            WorkforceJob.job_id == job_id,
            WorkforceJob.status == "RUNNING",
            WorkforceJob.lease_owner == worker_id,
        ).update(
            {
                WorkforceJob.lease_expires_at: now + timedelta(seconds=max(lease_seconds, 15)),
                WorkforceJob.updated_at: now,
            },
            synchronize_session=False,
        )
        db.commit()
        return changed == 1


def complete_job(job_id: str, worker_id: str, result: dict[str, Any]) -> bool:
    now = utcnow()
    with SessionLocal() as db:
        changed = db.query(WorkforceJob).filter(
            WorkforceJob.job_id == job_id,
            WorkforceJob.status == "RUNNING",
            WorkforceJob.lease_owner == worker_id,
        ).update(
            {
                WorkforceJob.status: "COMPLETED",
                WorkforceJob.result: result,
                WorkforceJob.last_error: None,
                WorkforceJob.lease_owner: None,
                WorkforceJob.lease_expires_at: None,
                WorkforceJob.completed_at: now,
                WorkforceJob.updated_at: now,
            },
            synchronize_session=False,
        )
        db.commit()
        return changed == 1


def fail_or_retry_job(job_id: str, worker_id: str, error: str) -> bool:
    now = utcnow()
    with SessionLocal() as db:
        job = db.query(WorkforceJob).filter(
            WorkforceJob.job_id == job_id,
            WorkforceJob.status == "RUNNING",
            WorkforceJob.lease_owner == worker_id,
        ).first()
        if job is None:
            return False
        retry = job.attempts < job.max_attempts and not job.cancel_requested
        delay = min(300, 5 * (2 ** max(job.attempts - 1, 0)))
        job.status = "PENDING" if retry else ("CANCELLED" if job.cancel_requested else "FAILED")
        job.available_at = now + timedelta(seconds=delay if retry else 0)
        job.last_error = error[:4000]
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = now
        db.commit()
    if retry:
        _notify_workers(job_id)
    return True


def cancel_job(*, job_id: str, company_id: str, tenant_id: str) -> dict[str, Any] | None:
    with SessionLocal() as db:
        job = db.query(WorkforceJob).filter(
            WorkforceJob.job_id == job_id,
            WorkforceJob.company_id == company_id,
            WorkforceJob.tenant_id == tenant_id,
        ).first()
        if job is None:
            return None
        if job.status == "PENDING":
            job.status = "CANCELLED"
            job.updated_at = utcnow()
        elif job.status == "RUNNING":
            job.cancel_requested = True
            job.updated_at = utcnow()
        db.commit()
        db.refresh(job)
        return _job_dict(job)


def recover_expired_jobs() -> int:
    """Requeue jobs whose worker lease expired; LangGraph checkpoints remain untouched."""
    now = utcnow()
    with SessionLocal() as db:
        expired = db.query(WorkforceJob).filter(
            WorkforceJob.status == "RUNNING",
            WorkforceJob.lease_expires_at.is_not(None),
            WorkforceJob.lease_expires_at < now,
        ).all()
        count = 0
        for job in expired:
            job.lease_owner = None
            job.lease_expires_at = None
            job.updated_at = now
            if job.cancel_requested:
                job.status = "CANCELLED"
            elif job.attempts >= job.max_attempts:
                job.status = "FAILED"
                job.last_error = (job.last_error or "Worker lease expired")[:4000]
            else:
                job.status = "PENDING"
                job.available_at = now
            count += 1
        db.commit()
        return count


def get_coordination(*, company_id: str, tenant_id: str) -> dict[str, Any] | None:
    with SessionLocal() as db:
        row = db.query(CompanyCoordination).filter(
            CompanyCoordination.company_id == company_id,
            CompanyCoordination.tenant_id == tenant_id,
        ).first()
        if row is None:
            return None
        return {
            "company_id": row.company_id,
            "tenant_id": row.tenant_id,
            "enabled": row.enabled,
            "mode": row.mode,
            "interval_seconds": row.interval_seconds,
            "next_run_at": row.next_run_at.isoformat() if row.next_run_at else None,
            "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
            "created_by": row.created_by,
        }


def configure_coordination(
    *, company_id: str, tenant_id: str, actor_id: str,
    enabled: bool, mode: str = "PLAN_ONLY", interval_seconds: int = 300,
) -> dict[str, Any]:
    if mode not in {"PLAN_ONLY", "AUTO_EXECUTE"}:
        raise ValueError("Coordination mode must be PLAN_ONLY or AUTO_EXECUTE")
    interval = min(max(int(interval_seconds), 60), 86400)
    if get_company_graph(company_id=company_id, tenant_id=tenant_id) is None:
        raise LookupError("Company not found")
    now = utcnow()
    with SessionLocal() as db:
        row = db.query(CompanyCoordination).filter(
            CompanyCoordination.company_id == company_id,
            CompanyCoordination.tenant_id == tenant_id,
        ).first()
        if row is None:
            row = CompanyCoordination(
                company_id=company_id,
                tenant_id=tenant_id,
                created_by=actor_id,
            )
            db.add(row)
        row.enabled = enabled
        row.mode = mode
        row.interval_seconds = interval
        row.next_run_at = now if enabled else now + timedelta(days=3650)
        row.updated_at = now
        db.commit()
    return get_coordination(company_id=company_id, tenant_id=tenant_id) or {}


def run_coordination_tick(limit: int = 50) -> int:
    """Convert due founder-approved company schedules into idempotent durable jobs."""
    now = utcnow()
    due: list[tuple[str, str, str, int]] = []
    with SessionLocal() as db:
        rows = db.query(CompanyCoordination).filter(
            CompanyCoordination.enabled.is_(True),
            CompanyCoordination.next_run_at <= now,
        ).order_by(CompanyCoordination.next_run_at.asc()).limit(limit).all()
        for row in rows:
            due.append((row.company_id, row.tenant_id, row.mode, row.interval_seconds))
            row.last_run_at = now
            row.next_run_at = now + timedelta(seconds=row.interval_seconds)
            row.updated_at = now
        db.commit()

    queued = 0
    for company_id, tenant_id, mode, interval in due:
        graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
        if graph is None:
            continue
        goals = [
            node for node in graph.get("nodes", [])
            if node["type"] == "goal" and node["status"] not in {"COMPLETED", "CANCELLED", "ARCHIVED"}
        ]
        for goal in goals:
            works = [
                node for node in graph.get("nodes", [])
                if node["type"] == "work" and (node.get("data") or {}).get("goal_id") == goal["id"]
            ]
            if not works:
                kind = "goal_plan"
            elif mode == "AUTO_EXECUTE" and any(node["status"] not in {"COMPLETED", "CANCELLED"} for node in works):
                kind = "goal_execution"
            else:
                continue
            bucket = int(now.timestamp()) // max(interval, 60)
            job = enqueue_job(
                company_id=company_id,
                tenant_id=tenant_id,
                kind=kind,
                target_id=goal["id"],
                actor_id="head_of_agents",
                idempotency_key=f"coordination:{goal['id']}:{kind}:{bucket}",
                payload={"source": "company_coordination", "mode": mode},
            )
            if not job.get("deduplicated"):
                queued += 1
    return queued


class DurableJobState(TypedDict, total=False):
    job_id: str
    company_id: str
    tenant_id: str
    actor_id: str
    kind: str
    target_id: str
    payload: dict[str, Any]
    result: dict[str, Any]
    error: str
    cancelled: bool


def build_job_graph(checkpointer):
    """Compile the LangGraph job state machine with the supplied checkpoint saver."""

    async def load_job(state: DurableJobState) -> dict[str, Any]:
        job = get_job(job_id=state["job_id"])
        if job is None:
            raise LookupError("Durable workforce job no longer exists")
        if job["cancel_requested"] or job["status"] == "CANCELLED":
            return {"cancelled": True}
        return {
            "company_id": job["company_id"],
            "tenant_id": job["tenant_id"],
            "actor_id": job["created_by"],
            "kind": job["kind"],
            "target_id": job["target_id"],
            "payload": job["payload"],
        }

    async def execute_job(state: DurableJobState) -> dict[str, Any]:
        if state.get("cancelled"):
            return {"result": {"status": "CANCELLED"}}
        from .workforce import plan_goal, execute_goal, execute_task, convene_meeting

        args = {
            "company_id": state["company_id"],
            "tenant_id": state["tenant_id"],
            "actor_id": state["actor_id"],
        }
        if state["kind"] == "goal_plan":
            result = await plan_goal(goal_id=state["target_id"], **args)
        elif state["kind"] == "goal_execution":
            result = await execute_goal(goal_id=state["target_id"], **args)
        elif state["kind"] == "work_execution":
            result = await execute_task(work_id=state["target_id"], **args)
        elif state["kind"] == "meeting":
            result = await convene_meeting(meeting_id=state["target_id"], **args)
        else:
            raise ValueError(f"Unsupported durable job kind: {state['kind']}")
        return {"result": result}

    async def persist_result(state: DurableJobState) -> dict[str, Any]:
        if state.get("cancelled"):
            return {"result": {"status": "CANCELLED"}}
        return {}

    builder = StateGraph(DurableJobState)
    builder.add_node("load_job", load_job)
    builder.add_node("execute_job", execute_job)
    builder.add_node("persist_result", persist_result)
    builder.set_entry_point("load_job")
    builder.add_edge("load_job", "execute_job")
    builder.add_edge("execute_job", "persist_result")
    builder.add_edge("persist_result", END)
    return builder.compile(checkpointer=checkpointer)


async def execute_durable_job(graph, job: dict[str, Any]) -> dict[str, Any]:
    config = {"configurable": {"thread_id": job["job_id"]}}
    result = await graph.ainvoke({"job_id": job["job_id"]}, config=config)
    return result.get("result") or {"status": "COMPLETED"}


async def _heartbeat_loop(job_id: str, worker_id: str, interval: int, lease_seconds: int) -> None:
    while True:
        await asyncio.sleep(max(5, interval))
        if not heartbeat_job(job_id, worker_id, lease_seconds):
            return


async def _wait_for_signal(redis_url: str, timeout: float) -> None:
    """Wait for a Valkey wake-up, falling back to polling on broker failure."""
    client = None
    pubsub = None
    try:
        from redis.asyncio import Redis

        client = Redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=0.5)
        pubsub = client.pubsub()
        await pubsub.subscribe("pinky-bread:workforce:jobs")
        await pubsub.get_message(ignore_subscribe_messages=True, timeout=0.05)
        await pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
    except Exception:
        await asyncio.sleep(timeout)
    finally:
        if pubsub is not None:
            try:
                await pubsub.aclose()
            except Exception:
                pass
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                pass


async def run_worker() -> None:
    """Run one durable worker process. Scale by running additional replicas."""
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    settings = get_settings()
    worker_id = f"pinky-worker-{uuid.uuid4()}"
    lease_seconds = max(settings.worker_lease_seconds, 30)
    heartbeat_interval = max(settings.worker_heartbeat_seconds, 5)
    dsn = settings.database_url.replace("postgresql+psycopg://", "postgresql://")
    if not dsn.startswith("postgresql://"):
        raise RuntimeError("The durable LangGraph worker requires PostgreSQL; configure DATABASE_URL")
    while True:
        try:
            recover_expired_jobs()
            run_coordination_tick()
            async with AsyncPostgresSaver.from_conn_string(dsn) as checkpointer:
                await checkpointer.setup()
                graph = build_job_graph(checkpointer)
                while True:
                    run_coordination_tick()
                    job = claim_next_job(worker_id, lease_seconds)
                    if job is None:
                        await _wait_for_signal(settings.redis_url, settings.worker_poll_seconds)
                        continue
                    heartbeat = asyncio.create_task(
                        _heartbeat_loop(job["job_id"], worker_id, heartbeat_interval, lease_seconds)
                    )
                    try:
                        result = await execute_durable_job(graph, job)
                        if result.get("status") == "CANCELLED":
                            with SessionLocal() as db:
                                db.query(WorkforceJob).filter(
                                    WorkforceJob.job_id == job["job_id"],
                                    WorkforceJob.lease_owner == worker_id,
                                ).update({
                                    WorkforceJob.status: "CANCELLED",
                                    WorkforceJob.lease_owner: None,
                                    WorkforceJob.lease_expires_at: None,
                                    WorkforceJob.updated_at: utcnow(),
                                }, synchronize_session=False)
                                db.commit()
                        else:
                            complete_job(job["job_id"], worker_id, result)
                    except Exception as exc:
                        fail_or_retry_job(job["job_id"], worker_id, f"{type(exc).__name__}: {exc}")
                    finally:
                        heartbeat.cancel()
                        try:
                            await heartbeat
                        except asyncio.CancelledError:
                            pass
        except asyncio.CancelledError:
            raise
        except Exception:
            # Database or checkpoint outages are retried by the outer worker loop.
            await asyncio.sleep(max(settings.worker_poll_seconds, 2))
