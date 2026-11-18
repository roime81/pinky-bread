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


def test_one_agent_can_contribute_to_multiple_goals_and_kpi_measures_goal():
    init_db()
    with TestClient(app) as client:
        company = client.post("/v2/companies", json={
            "tenant_id": "many-to-many-tenant",
            "owner_id": "founder",
            "name": "Many-to-many Company",
        }).json()
        company_id = company["id"]

        def create_node(node_type, name):
            response = client.post(f"/v2/companies/{company_id}/nodes", json={
                "tenant_id": "many-to-many-tenant",
                "actor_id": "founder",
                "node_type": node_type,
                "name": name,
            })
            assert response.status_code == 201, response.text
            return response.json()

        goal_a = create_node("goal", "Launch the SaaS product")
        goal_b = create_node("goal", "Acquire first customers")
        agent = create_node("agent", "Growth and Product Agent")
        kpi = create_node("kpi", "Paying customers")

        def connect(source, target, relationship):
            response = client.post(f"/v2/companies/{company_id}/edges", json={
                "tenant_id": "many-to-many-tenant",
                "actor_id": "founder",
                "source_node_id": source["id"],
                "target_node_id": target["id"],
                "relationship": relationship,
            })
            assert response.status_code == 201, response.text

        connect(agent, goal_a, "contributes_to")
        connect(agent, goal_b, "contributes_to")
        connect(goal_b, kpi, "measures")

        graph = client.get(
            f"/v2/companies/{company_id}/graph?tenant_id=many-to-many-tenant"
        ).json()
        agent_nodes = [node for node in graph["nodes"] if node["id"] == agent["id"]]
        assert len(agent_nodes) == 1

        contributions = [
            edge for edge in graph["edges"]
            if edge["source"] == agent["id"] and edge["relationship"] == "contributes_to"
        ]
        assert {edge["target"] for edge in contributions} == {goal_a["id"], goal_b["id"]}

        measures = [
            edge for edge in graph["edges"]
            if edge["source"] == goal_b["id"] and edge["target"] == kpi["id"]
        ]
        assert len(measures) == 1
        assert measures[0]["relationship"] == "measures"


def test_object_store_rejects_traversal_and_round_trips_local_bytes(tmp_path, monkeypatch):
    from app.object_store import ObjectStore
    from app.settings import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "upload_dir", tmp_path)
    store = ObjectStore()

    key = "companies/example/documents/brief.txt"
    uri = store.put_bytes(key, b"company plan", "text/plain")
    assert uri.startswith("file://")
    assert store.get_bytes(key) == b"company plan"
    store.delete(key)
    try:
        store.get_bytes(key)
        assert False, "deleted object should not be readable"
    except FileNotFoundError:
        pass

    for unsafe in ("../secret.txt", "companies/../../secret.txt", "/absolute/path"):
        try:
            store.put_bytes(unsafe, b"bad", "text/plain")
            assert False, f"unsafe object key should be rejected: {unsafe}"
        except ValueError:
            pass


def test_company_artifacts_are_catalogued_in_database_and_downloaded_from_store():
    init_db()
    with TestClient(app) as client:
        company = client.post("/v2/companies", json={
            "tenant_id": "artifact-tenant",
            "owner_id": "founder",
            "name": "Artifact Studio",
        }).json()
        company_id = company["id"]
        goal = client.post(f"/v2/companies/{company_id}/nodes", json={
            "tenant_id": "artifact-tenant",
            "actor_id": "founder",
            "node_type": "goal",
            "name": "Prepare company strategy",
        }).json()

        upload = client.post(
            f"/v2/companies/{company_id}/artifacts",
            data={
                "tenant_id": "artifact-tenant",
                "actor_id": "founder",
                "kind": "document",
                "title": "Strategy brief",
                "related_node_id": goal["id"],
            },
            files={"file": ("strategy.txt", b"company vision and strategy", "text/plain")},
        )
        assert upload.status_code == 201, upload.text
        artifact = upload.json()["artifact"]
        assert artifact["filename"] == "strategy.txt"
        assert artifact["size_bytes"] == len(b"company vision and strategy")
        assert len(artifact["sha256"]) == 64

        listed = client.get(
            f"/v2/companies/{company_id}/artifacts?tenant_id=artifact-tenant"
        )
        assert listed.status_code == 200
        assert listed.json()["artifacts"][0]["object_id"] == artifact["object_id"]

        downloaded = client.get(
            f"/v2/companies/{company_id}/artifacts/{artifact['object_id']}?tenant_id=artifact-tenant"
        )
        assert downloaded.status_code == 200
        assert downloaded.content == b"company vision and strategy"

        wrong_tenant = client.get(
            f"/v2/companies/{company_id}/artifacts/{artifact['object_id']}?tenant_id=other-tenant"
        )
        assert wrong_tenant.status_code == 404

        graph = client.get(
            f"/v2/companies/{company_id}/graph?tenant_id=artifact-tenant"
        ).json()
        doc = next(node for node in graph["nodes"] if node["data"].get("object_id") == artifact["object_id"])
        assert doc["type"] == "document"
        assert any(
            edge["source"] == doc["id"] and edge["target"] == goal["id"] and edge["relationship"] == "informs"
            for edge in graph["edges"]
        )
