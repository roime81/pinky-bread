from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app


def test_company_graph_persists_nodes_edges_and_verified_events():
    init_db()
    with TestClient(app) as client:
        created = client.post("/v2/companies", json={
            "tenant_id": "graph-test-tenant",
            "owner_id": "graph-test-founder",
            "name": "Graph Test Studio",
            "vision": "Build useful software",
            "mission": "Create and ship a product",
            "values": ["clarity", "trust"],
        })
        assert created.status_code == 201, created.text
        company = created.json()
        company_id = company["id"]

        goal_response = client.post(f"/v2/companies/{company_id}/nodes", json={
            "tenant_id": "graph-test-tenant",
            "actor_id": "graph-test-founder",
            "node_type": "goal",
            "name": "Launch the first product",
            "description": "Reach the first paying customers",
            "status": "PLANNED",
            "data": {"progress": 0, "target_customers": 10},
        })
        assert goal_response.status_code == 201, goal_response.text
        goal = goal_response.json()

        edge_response = client.post(f"/v2/companies/{company_id}/edges", json={
            "tenant_id": "graph-test-tenant",
            "actor_id": "graph-test-founder",
            "source_node_id": company_id,
            "target_node_id": goal["id"],
            "relationship": "owns",
            "data": {},
        })
        assert edge_response.status_code == 201, edge_response.text

        graph_response = client.get(f"/v2/companies/{company_id}/graph?tenant_id=graph-test-tenant")
        assert graph_response.status_code == 200
        graph = graph_response.json()
        assert {node["type"] for node in graph["nodes"]} == {"company", "goal"}
        assert len(graph["edges"]) == 1
        assert graph["edges"][0]["relationship"] == "owns"

        events_response = client.get(f"/v2/companies/{company_id}/events?tenant_id=graph-test-tenant")
        assert events_response.status_code == 200
        assert events_response.json()["count"] == 3

        verification = client.get(
            f"/v2/companies/{company_id}/events/verify?tenant_id=graph-test-tenant"
        )
        assert verification.status_code == 200
        assert verification.json()["valid"] is True
        assert verification.json()["checked_events"] == 3

        wrong_tenant = client.get(f"/v2/companies/{company_id}/graph?tenant_id=other-tenant")
        assert wrong_tenant.status_code == 404


def test_company_graph_rejects_unsupported_node_types_and_cross_company_edges():
    init_db()
    with TestClient(app) as client:
        first = client.post("/v2/companies", json={
            "tenant_id": "graph-isolation-tenant",
            "owner_id": "founder",
            "name": "First Company",
        }).json()
        second = client.post("/v2/companies", json={
            "tenant_id": "graph-isolation-tenant",
            "owner_id": "founder",
            "name": "Second Company",
        }).json()

        unsupported = client.post(f"/v2/companies/{first['id']}/nodes", json={
            "tenant_id": "graph-isolation-tenant",
            "actor_id": "founder",
            "node_type": "unknown",
            "name": "Invalid node",
        })
        assert unsupported.status_code == 422

        node = client.post(f"/v2/companies/{second['id']}/nodes", json={
            "tenant_id": "graph-isolation-tenant",
            "actor_id": "founder",
            "node_type": "agent",
            "name": "Second company agent",
        }).json()

        cross_company_edge = client.post(f"/v2/companies/{first['id']}/edges", json={
            "tenant_id": "graph-isolation-tenant",
            "actor_id": "founder",
            "source_node_id": first["id"],
            "target_node_id": node["id"],
            "relationship": "owns",
        })
        assert cross_company_edge.status_code == 422
