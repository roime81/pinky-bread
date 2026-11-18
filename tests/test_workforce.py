from fastapi.testclient import TestClient

from app.database import init_db
from app.main import app
from app.settings import get_settings


def _create_company(client: TestClient, tenant: str, name: str = "Workforce Test Co"):
    response = client.post("/v2/companies", json={
        "tenant_id": tenant,
        "owner_id": "founder",
        "name": name,
        "vision": "Build a sustainable small business",
        "mission": "Serve customers with useful products",
        "values": ["clarity", "trust"],
    })
    assert response.status_code == 201, response.text
    return response.json()


def _create_node(client: TestClient, company_id: str, tenant: str, kind: str, name: str, data=None):
    response = client.post(f"/v2/companies/{company_id}/nodes", json={
        "tenant_id": tenant,
        "actor_id": "founder",
        "node_type": kind,
        "name": name,
        "description": "Test description",
        "status": "PLANNED",
        "data": data or {},
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_workforce_bootstrap_is_persistent_and_idempotent():
    init_db()
    with TestClient(app) as client:
        company = _create_company(client, "workforce-bootstrap-tenant")
        url = f"/v2/companies/{company['id']}/workforce/bootstrap"
        payload = {"tenant_id": "workforce-bootstrap-tenant", "actor_id": "founder"}
        first = client.post(url, json=payload)
        second = client.post(url, json=payload)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["count"] == 7
        assert second.json()["count"] == 7
        graph = client.get(
            f"/v2/companies/{company['id']}/graph?tenant_id=workforce-bootstrap-tenant"
        ).json()
        agents = [node for node in graph["nodes"] if node["type"] == "agent"]
        assert len(agents) == 7
        assert {node["data"]["role"] for node in agents} == {
            "head_of_agents", "strategy", "product", "technology",
            "marketing", "operations", "finance",
        }
        assert sum(1 for node in agents if node["data"]["role"] == "head_of_agents") == 1


def test_head_of_agents_plans_goal_into_database_assignments_without_duplicates():
    init_db()
    settings = get_settings()
    settings.mock_inference = True
    with TestClient(app) as client:
        company = _create_company(client, "goal-plan-tenant")
        goal = _create_node(client, company["id"], "goal-plan-tenant", "goal", "Launch a small SaaS product")
        url = f"/v2/companies/{company['id']}/goals/{goal['id']}/plan"
        payload = {"tenant_id": "goal-plan-tenant", "actor_id": "founder"}
        first = client.post(url, json=payload)
        second = client.post(url, json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["created"] is True
        assert first.json()["planner_mode"] == "mock-template"
        assert first.json()["count"] == 6
        assert second.status_code == 200, second.text
        assert second.json()["created"] is False
        assert second.json()["count"] == 6

        graph = client.get(
            f"/v2/companies/{company['id']}/graph?tenant_id=goal-plan-tenant"
        ).json()
        tasks = [
            node for node in graph["nodes"]
            if node["type"] == "work" and node["data"].get("goal_id") == goal["id"]
        ]
        assert len(tasks) == 6
        assignments = [
            edge for edge in graph["edges"]
            if edge["relationship"] == "assigned_to"
            and any(task["id"] == edge["source"] for task in tasks)
        ]
        assert len(assignments) == 6
        assert len({edge["target"] for edge in assignments}) >= 5
        dependency_edges = [edge for edge in graph["edges"] if edge["relationship"] == "depends_on"]
        assert len(dependency_edges) >= 4


def test_goal_execution_persists_deliverables_and_updates_goal_progress():
    init_db()
    settings = get_settings()
    settings.mock_inference = True
    with TestClient(app) as client:
        company = _create_company(client, "goal-run-tenant")
        goal = _create_node(client, company["id"], "goal-run-tenant", "goal", "Prepare a product launch")
        response = client.post(
            f"/v2/companies/{company['id']}/goals/{goal['id']}/execute",
            json={"tenant_id": "goal-run-tenant", "actor_id": "founder"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["completed"] == 6
        assert result["errors"] == []
        assert result["progress"]["progress"] == 100

        graph = client.get(
            f"/v2/companies/{company['id']}/graph?tenant_id=goal-run-tenant"
        ).json()
        goal_node = next(node for node in graph["nodes"] if node["id"] == goal["id"])
        tasks = [
            node for node in graph["nodes"]
            if node["type"] == "work" and node["data"].get("goal_id") == goal["id"]
        ]
        deliverables = [
            node for node in graph["nodes"]
            if node["type"] == "deliverable" and node["data"].get("goal_id") == goal["id"]
        ]
        assert goal_node["status"] == "COMPLETED"
        assert goal_node["data"]["progress"] == 100
        assert len(tasks) == 6
        assert all(task["status"] == "COMPLETED" for task in tasks)
        assert len(deliverables) == 6
        assert all(item["data"].get("object_id") for item in deliverables)

        artifact = deliverables[0]["data"]["object_id"]
        download = client.get(
            f"/v2/companies/{company['id']}/artifacts/{artifact}?tenant_id=goal-run-tenant"
        )
        assert download.status_code == 200
        assert b"MOCK" in download.content


def test_meeting_convenes_agents_and_stores_minutes_as_company_deliverable():
    init_db()
    settings = get_settings()
    settings.mock_inference = True
    with TestClient(app) as client:
        company = _create_company(client, "meeting-runtime-tenant")
        meeting = _create_node(
            client, company["id"], "meeting-runtime-tenant", "meeting",
            "Weekly company alignment",
            {"meeting_type": "alignment", "meeting_state": "DRAFT", "agenda": "Review goal progress and risks"},
        )
        response = client.post(
            f"/v2/companies/{company['id']}/meetings/{meeting['id']}/convene",
            json={"tenant_id": "meeting-runtime-tenant", "actor_id": "founder"},
        )
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["idempotent"] is False
        assert len(result["participants"]) == 5
        assert result["meeting"]["status"] == "COMPLETED"
        assert result["meeting"]["data"]["meeting_state"] == "COMPLETED"
        assert result["meeting"]["data"]["minutes_object_id"]
        assert result["deliverable"]["type"] == "deliverable"

        again = client.post(
            f"/v2/companies/{company['id']}/meetings/{meeting['id']}/convene",
            json={"tenant_id": "meeting-runtime-tenant", "actor_id": "founder"},
        )
        assert again.status_code == 200, again.text
        assert again.json()["idempotent"] is True


def test_kpi_measurements_are_versioned_in_company_node_and_event_history():
    init_db()
    with TestClient(app) as client:
        company = _create_company(client, "kpi-runtime-tenant")
        kpi = _create_node(
            client, company["id"], "kpi-runtime-tenant", "kpi", "Paying customers",
            {"target": 20, "unit": "customers", "actual": None},
        )
        response = client.post(
            f"/v2/companies/{company['id']}/kpis/{kpi['id']}/measure",
            json={
                "tenant_id": "kpi-runtime-tenant",
                "actor_id": "founder",
                "actual_value": 8,
                "source": "Founder-reported CRM count",
                "evidence": "Eight active paid subscriptions",
            },
        )
        assert response.status_code == 200, response.text
        assert response.json()["kpi"]["data"]["actual"] == 8
        assert response.json()["kpi"]["status"] == "TRACKING"
        assert response.json()["history_count"] == 1
        verify = client.get(
            f"/v2/companies/{company['id']}/events/verify?tenant_id=kpi-runtime-tenant"
        )
        assert verify.status_code == 200
        assert verify.json()["valid"] is True
