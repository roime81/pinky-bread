from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from .company_graph import (
    NODE_TYPES,
    RELATIONSHIPS,
    create_company,
    create_edge,
    create_node,
    get_company_graph,
    list_companies,
    list_company_events,
    verify_event_chain,
)

router = APIRouter(prefix="/v2", tags=["company graph"])


class CompanyCreate(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    owner_id: str = Field(default="demo-user", min_length=2, max_length=120)
    name: str = Field(min_length=2, max_length=240)
    vision: str = Field(default="", max_length=4000)
    mission: str = Field(default="", max_length=4000)
    values: list[str] = Field(default_factory=list, max_length=30)


class GraphNodeCreate(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    actor_id: str = Field(default="demo-user", min_length=2, max_length=120)
    node_type: str
    name: str = Field(min_length=1, max_length=240)
    description: str = Field(default="", max_length=8000)
    status: str = Field(default="PLANNED", min_length=2, max_length=40)
    data: dict[str, Any] = Field(default_factory=dict)


class GraphEdgeCreate(BaseModel):
    tenant_id: str = Field(default="demo-tenant", min_length=2, max_length=120)
    actor_id: str = Field(default="demo-user", min_length=2, max_length=120)
    source_node_id: str = Field(min_length=36, max_length=36)
    target_node_id: str = Field(min_length=36, max_length=36)
    relationship: str
    data: dict[str, Any] = Field(default_factory=dict)


@router.get("/capabilities")
def company_graph_capabilities() -> dict[str, Any]:
    return {
        "version": "2.0.0-alpha.1",
        "node_types": sorted(NODE_TYPES | {"company"}),
        "relationships": sorted(RELATIONSHIPS),
        "persistence": "SQLAlchemy relational database",
        "event_log": "append-only hash-linked database records",
        "live_notifications": "Valkey/Redis-compatible PubSub when configured",
        "source_of_truth": "database",
    }


@router.post("/companies", status_code=201)
def create_company_endpoint(request: CompanyCreate) -> dict[str, Any]:
    return create_company(
        tenant_id=request.tenant_id,
        owner_id=request.owner_id,
        name=request.name,
        vision=request.vision,
        mission=request.mission,
        values=request.values,
    )


@router.get("/companies")
def list_companies_endpoint(
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    return {"companies": list_companies(tenant_id=tenant_id)}


@router.get("/companies/{company_id}/graph")
def get_graph_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    graph = get_company_graph(company_id=company_id, tenant_id=tenant_id)
    if graph is None:
        raise HTTPException(404, "Company not found")
    return graph


@router.post("/companies/{company_id}/nodes", status_code=201)
def create_node_endpoint(company_id: str, request: GraphNodeCreate) -> dict[str, Any]:
    if request.node_type not in NODE_TYPES:
        raise HTTPException(422, f"Unsupported node type. Allowed: {', '.join(sorted(NODE_TYPES))}")
    try:
        node = create_node(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            node_type=request.node_type,
            name=request.name,
            description=request.description,
            status=request.status,
            data=request.data,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if node is None:
        raise HTTPException(404, "Company not found")
    return node


@router.post("/companies/{company_id}/edges", status_code=201)
def create_edge_endpoint(company_id: str, request: GraphEdgeCreate) -> dict[str, Any]:
    if request.relationship not in RELATIONSHIPS:
        raise HTTPException(422, f"Unsupported relationship. Allowed: {', '.join(sorted(RELATIONSHIPS))}")
    try:
        edge = create_edge(
            company_id=company_id,
            tenant_id=request.tenant_id,
            actor_id=request.actor_id,
            source_node_id=request.source_node_id,
            target_node_id=request.target_node_id,
            relationship=request.relationship,
            data=request.data,
        )
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    if edge is None:
        raise HTTPException(404, "Company not found")
    return edge


@router.get("/companies/{company_id}/events")
def list_events_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
    after_event_no: int = Query(default=0, ge=0),
    limit: int = Query(default=200, ge=1, le=1000),
) -> dict[str, Any]:
    events = list_company_events(
        company_id=company_id,
        tenant_id=tenant_id,
        after_event_no=after_event_no,
        limit=limit,
    )
    if events is None:
        raise HTTPException(404, "Company not found")
    return {"events": events, "count": len(events)}


@router.get("/companies/{company_id}/events/verify")
def verify_events_endpoint(
    company_id: str,
    tenant_id: str = Query(default="demo-tenant", min_length=2, max_length=120),
) -> dict[str, Any]:
    result = verify_event_chain(company_id=company_id, tenant_id=tenant_id)
    if result is None:
        raise HTTPException(404, "Company not found")
    return result
