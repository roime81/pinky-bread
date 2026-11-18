from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import JSON, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base, SessionLocal
from .settings import get_settings


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CompanyGraphNode(Base):
    """Canonical company, goal, KPI, agent, work and collaboration records."""

    __tablename__ = "company_graph_nodes"
    __table_args__ = (
        Index("ix_company_graph_company_type", "company_id", "node_type"),
        Index("ix_company_graph_company_status", "company_id", "status"),
    )

    node_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    node_type: Mapped[str] = mapped_column(String(40), index=True)
    name: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="ACTIVE", index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class CompanyGraphEdge(Base):
    """A directed, typed relationship between two nodes in one company graph."""

    __tablename__ = "company_graph_edges"
    __table_args__ = (
        UniqueConstraint("company_id", "source_node_id", "target_node_id", "relationship", name="uq_company_graph_edge"),
        Index("ix_company_graph_edge_source", "company_id", "source_node_id"),
        Index("ix_company_graph_edge_target", "company_id", "target_node_id"),
    )

    edge_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    source_node_id: Mapped[str] = mapped_column(String(36), index=True)
    target_node_id: Mapped[str] = mapped_column(String(36), index=True)
    relationship: Mapped[str] = mapped_column(String(60), index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_by: Mapped[str] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class CompanyGraphEvent(Base):
    """Append-only event history; the database is authoritative, Valkey is notification-only."""

    __tablename__ = "company_graph_events"

    event_no: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(String(36), unique=True, index=True)
    company_id: Mapped[str] = mapped_column(String(36), index=True)
    tenant_id: Mapped[str] = mapped_column(String(120), index=True)
    actor_id: Mapped[str] = mapped_column(String(120))
    event_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    occurred_at: Mapped[str] = mapped_column(String(40))
    previous_hash: Mapped[str] = mapped_column(String(64))
    entry_hash: Mapped[str] = mapped_column(String(64), index=True)


NODE_TYPES = {
    "goal", "kpi", "agent", "department", "work", "meeting",
    "decision", "deliverable", "document", "customer", "integration",
}
RELATIONSHIPS = {
    "owns", "reports_to", "contributes_to", "assigned_to", "depends_on",
    "collaborates_with", "participates_in", "produces", "measures",
    "blocks", "informs", "approved_by",
}


def _node_dict(node: CompanyGraphNode) -> dict[str, Any]:
    return {
        "id": node.node_id,
        "company_id": node.company_id,
        "tenant_id": node.tenant_id,
        "type": node.node_type,
        "name": node.name,
        "description": node.description,
        "status": node.status,
        "data": node.data or {},
        "created_by": node.created_by,
        "created_at": node.created_at.isoformat() if node.created_at else None,
        "updated_at": node.updated_at.isoformat() if node.updated_at else None,
    }


def _edge_dict(edge: CompanyGraphEdge) -> dict[str, Any]:
    return {
        "id": edge.edge_id,
        "source": edge.source_node_id,
        "target": edge.target_node_id,
        "relationship": edge.relationship,
        "data": edge.data or {},
        "created_by": edge.created_by,
        "created_at": edge.created_at.isoformat() if edge.created_at else None,
    }


def _event_dict(event: CompanyGraphEvent) -> dict[str, Any]:
    return {
        "event_no": event.event_no,
        "id": event.event_id,
        "company_id": event.company_id,
        "actor_id": event.actor_id,
        "type": event.event_type,
        "payload": event.payload or {},
        "occurred_at": event.occurred_at,
        "previous_hash": event.previous_hash,
        "entry_hash": event.entry_hash,
    }


def _append_event(
    db,
    *,
    company_id: str,
    tenant_id: str,
    actor_id: str,
    event_type: str,
    payload: dict[str, Any],
) -> CompanyGraphEvent:
    # Serialize event-chain writes for PostgreSQL. SQLite remains suitable for
    # single-process development but does not provide this row-lock guarantee.
    db.query(CompanyGraphNode).filter(
        CompanyGraphNode.node_id == company_id,
        CompanyGraphNode.tenant_id == tenant_id,
        CompanyGraphNode.node_type == "company",
    ).with_for_update().first()

    previous = (
        db.query(CompanyGraphEvent.entry_hash)
        .filter(CompanyGraphEvent.company_id == company_id, CompanyGraphEvent.tenant_id == tenant_id)
        .order_by(CompanyGraphEvent.event_no.desc())
        .limit(1)
        .scalar()
    ) or "GENESIS"
    occurred_at = utcnow().isoformat()
    event_id = str(uuid.uuid4())
    canonical = {
        "id": event_id,
        "company_id": company_id,
        "tenant_id": tenant_id,
        "actor_id": actor_id,
        "type": event_type,
        "payload": payload,
        "occurred_at": occurred_at,
        "previous_hash": previous,
    }
    entry_hash = hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()
    event = CompanyGraphEvent(
        event_id=event_id,
        company_id=company_id,
        tenant_id=tenant_id,
        actor_id=actor_id,
        event_type=event_type,
        payload=payload,
        occurred_at=occurred_at,
        previous_hash=previous,
        entry_hash=entry_hash,
    )
    db.add(event)
    db.flush()
    return event


def _notify(event: dict[str, Any]) -> None:
    """Best-effort live notification; durable replay always comes from PostgreSQL."""
    try:
        from redis import Redis

        settings = get_settings()
        client = Redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=0.25,
            socket_timeout=0.25,
        )
        client.publish(
            f"pinky-bread:company:{event['company_id']}",
            json.dumps(event, ensure_ascii=False, default=str),
        )
        client.close()
    except Exception:
        # A broker outage must never roll back a committed company mutation.
        return

def _company_exists(db, company_id: str, tenant_id: str) -> CompanyGraphNode | None:
    return db.query(CompanyGraphNode).filter(
        CompanyGraphNode.node_id == company_id,
        CompanyGraphNode.company_id == company_id,
        CompanyGraphNode.tenant_id == tenant_id,
        CompanyGraphNode.node_type == "company",
    ).first()


def create_company(
    *, tenant_id: str, owner_id: str, name: str, vision: str, mission: str, values: list[str]
) -> dict[str, Any]:
    company_id = str(uuid.uuid4())
    payload = {"vision": vision, "mission": mission, "values": values}
    with SessionLocal() as db:
        node = CompanyGraphNode(
            node_id=company_id,
            company_id=company_id,
            tenant_id=tenant_id,
            node_type="company",
            name=name,
            description=mission,
            status="ACTIVE",
            data=payload,
            created_by=owner_id,
        )
        db.add(node)
        event = _append_event(
            db,
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=owner_id,
            event_type="company.created",
            payload={"node_id": company_id, "name": name, **payload},
        )
        db.commit()
        result = _node_dict(node)
        event_data = _event_dict(event)
    _notify(event_data)
    return result



def list_companies(*, tenant_id: str) -> list[dict[str, Any]]:
    with SessionLocal() as db:
        rows = (
            db.query(CompanyGraphNode)
            .filter(CompanyGraphNode.tenant_id == tenant_id, CompanyGraphNode.node_type == "company")
            .order_by(CompanyGraphNode.created_at.asc())
            .all()
        )
        return [_node_dict(row) for row in rows]


def get_company_graph(*, company_id: str, tenant_id: str) -> dict[str, Any] | None:
    with SessionLocal() as db:
        company = _company_exists(db, company_id, tenant_id)
        if not company:
            return None
        nodes = (
            db.query(CompanyGraphNode)
            .filter(CompanyGraphNode.company_id == company_id, CompanyGraphNode.tenant_id == tenant_id)
            .order_by(CompanyGraphNode.created_at.asc())
            .all()
        )
        edges = (
            db.query(CompanyGraphEdge)
            .filter(CompanyGraphEdge.company_id == company_id, CompanyGraphEdge.tenant_id == tenant_id)
            .order_by(CompanyGraphEdge.created_at.asc())
            .all()
        )
        latest_event = (
            db.query(CompanyGraphEvent.event_no)
            .filter(CompanyGraphEvent.company_id == company_id, CompanyGraphEvent.tenant_id == tenant_id)
            .order_by(CompanyGraphEvent.event_no.desc())
            .limit(1)
            .scalar()
        ) or 0
        return {
            "company_id": company_id,
            "version": 1,
            "latest_event_no": latest_event,
            "nodes": [_node_dict(node) for node in nodes],
            "edges": [_edge_dict(edge) for edge in edges],
        }


def create_node(
    *,
    company_id: str,
    tenant_id: str,
    actor_id: str,
    node_type: str,
    name: str,
    description: str,
    status: str,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    if node_type not in NODE_TYPES:
        raise ValueError(f"Unsupported node type: {node_type}")
    node_id = str(uuid.uuid4())
    with SessionLocal() as db:
        if not _company_exists(db, company_id, tenant_id):
            return None
        node = CompanyGraphNode(
            node_id=node_id,
            company_id=company_id,
            tenant_id=tenant_id,
            node_type=node_type,
            name=name,
            description=description,
            status=status,
            data=data,
            created_by=actor_id,
        )
        db.add(node)
        event = _append_event(
            db,
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type=f"{node_type}.created",
            payload={"node_id": node_id, "name": name, "status": status, "data": data},
        )
        db.commit()
        result = _node_dict(node)
        event_data = _event_dict(event)
    _notify(event_data)
    return result


def create_edge(
    *,
    company_id: str,
    tenant_id: str,
    actor_id: str,
    source_node_id: str,
    target_node_id: str,
    relationship: str,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    if relationship not in RELATIONSHIPS:
        raise ValueError(f"Unsupported relationship: {relationship}")
    edge_id = str(uuid.uuid4())
    with SessionLocal() as db:
        if not _company_exists(db, company_id, tenant_id):
            return None
        endpoints = (
            db.query(CompanyGraphNode)
            .filter(
                CompanyGraphNode.company_id == company_id,
                CompanyGraphNode.tenant_id == tenant_id,
                CompanyGraphNode.node_id.in_([source_node_id, target_node_id]),
            )
            .all()
        )
        if len({node.node_id for node in endpoints}) != 2:
            raise ValueError("Both edge endpoints must belong to this company and tenant")
        edge = CompanyGraphEdge(
            edge_id=edge_id,
            company_id=company_id,
            tenant_id=tenant_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            relationship=relationship,
            data=data,
            created_by=actor_id,
        )
        db.add(edge)
        event = _append_event(
            db,
            company_id=company_id,
            tenant_id=tenant_id,
            actor_id=actor_id,
            event_type="graph.edge.created",
            payload={
                "edge_id": edge_id,
                "source": source_node_id,
                "target": target_node_id,
                "relationship": relationship,
            },
        )
        db.commit()
        result = _edge_dict(edge)
        event_data = _event_dict(event)
    _notify(event_data)
    return result


def list_company_events(
    *, company_id: str, tenant_id: str, after_event_no: int = 0, limit: int = 200
) -> list[dict[str, Any]] | None:
    with SessionLocal() as db:
        if not _company_exists(db, company_id, tenant_id):
            return None
        rows = (
            db.query(CompanyGraphEvent)
            .filter(
                CompanyGraphEvent.company_id == company_id,
                CompanyGraphEvent.tenant_id == tenant_id,
                CompanyGraphEvent.event_no > after_event_no,
            )
            .order_by(CompanyGraphEvent.event_no.asc())
            .limit(min(max(limit, 1), 1000))
            .all()
        )
        return [_event_dict(row) for row in rows]


def verify_event_chain(*, company_id: str, tenant_id: str) -> dict[str, Any] | None:
    events: list[dict[str, Any]] = []
    after_event_no = 0
    while True:
        batch = list_company_events(
            company_id=company_id,
            tenant_id=tenant_id,
            after_event_no=after_event_no,
            limit=1000,
        )
        if batch is None:
            return None
        if not batch:
            break
        events.extend(batch)
        after_event_no = batch[-1]["event_no"]

    previous = "GENESIS"
    for index, item in enumerate(events):
        canonical = {
            "id": item["id"],
            "company_id": company_id,
            "tenant_id": tenant_id,
            "actor_id": item["actor_id"],
            "type": item["type"],
            "payload": item["payload"],
            "occurred_at": item["occurred_at"],
            "previous_hash": previous,
        }
        expected = hashlib.sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str).encode("utf-8")
        ).hexdigest()
        if item["previous_hash"] != previous or item["entry_hash"] != expected:
            return {"valid": False, "checked_events": index, "failed_event_no": item["event_no"]}
        previous = item["entry_hash"]
    return {"valid": True, "checked_events": len(events), "latest_hash": previous}
