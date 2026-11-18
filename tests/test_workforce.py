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


def _create_agent(
    client: TestClient,
    company_id: str,
    tenant: str,
    name: str,
    role: str,
    *,
    title: str | None = None,
    authority: str = "SPECIALIST",
    manager_id: str | None = None,
    seniority_level: int = 3,
):
    response = client.post(f"/v2/companies/{company_id}/agents", json={
        "tenant_id": tenant,
        "actor_id": "founder",
        "name": name,
        "role": role,
        "title": title or role,
        "description": f"Responsible for {role}",
        "skills": [role.lower().replace(" ", "_")],
        "responsibilities": [f"Deliver work in {role}"],
        "system_prompt": f"You are {name}. Focus on {role}.",
        "authority": authority,
        "seniority_level": seniority_level,
        "manager_id": manager_id,
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_workforce_bootstrap_is_compatible_but_does_not_create_a_predefined_roster():
    init_db()
    with TestClient(app) as client:
        company = _create_company(client, "workforce-bootstrap-tenant")
        url = f"/v2/companies/{company['id']}/workforce/bootstrap"
        payload = {"tenant_id": "workforce-bootstrap-tenant", "actor_id": "founder"}
        first = client.post(url, json=payload)
        second = client.post(url, json=payload)
        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert first.json()["count"] == 0
        assert second.json()["count"] == 0
        assert first.json()["created"] == 0
        assert "No default roster" in first.json()["message"]
        graph = client.get(
            f"/v2/companies/{company['id']}/graph?tenant_id=workforce-bootstrap-tenant"
        ).json()
        assert [node for node in graph["nodes"] if node["type"] == "agent"] == []


def test_head_of_agents_plans_goal_into_database_assignments_without_duplicates():
    init_db()
    settings = get_settings()
    settings.mock_inference = True
    with TestClient(app) as client:
        company = _create_company(client, "goal-plan-tenant")
        coordinator = _create_agent(
            client, company["id"], "goal-plan-tenant", "Nora", "Company coordination",
            title="Head of Agents", authority="COORDINATOR",
        )
        specialists = [
            _create_agent(client, company["id"], "goal-plan-tenant", f"Agent {index}", f"Specialist function {index}")
            for index in range(1, 7)
        ]
        goal = _create_node(client, company["id"], "goal-plan-tenant", "goal", "Launch a small SaaS product")
        url = f"/v2/companies/{company['id']}/goals/{goal['id']}/plan"
        payload = {"tenant_id": "goal-plan-tenant", "actor_id": "founder"}
        first = client.post(url, json=payload)
        second = client.post(url, json=payload)
        assert first.status_code == 200, first.text
        assert first.json()["created"] is True
        assert first.json()["planner_mode"] == "mock-template-from-company-agents"
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
        assert {node["data"]["assigned_agent_id"] for node in tasks} == {agent["id"] for agent in specialists}
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
        _create_agent(client, company["id"], "goal-run-tenant", "Nora", "Company coordination", title="Chief of Staff", authority="COORDINATOR")
        for index in range(1, 7):
            _create_agent(client, company["id"], "goal-run-tenant", f"Custom Agent {index}", f"Founder-defined function {index}")
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
        _create_agent(client, company["id"], "meeting-runtime-tenant", "Avery", "Company coordination", title="Virtual Chief of Staff", authority="COORDINATOR")
        for index in range(1, 5):
            _create_agent(client, company["id"], "meeting-runtime-tenant", f"Meeting Agent {index}", f"Special function {index}")
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


def test_agent_management_supports_custom_profiles_seniority_archive_and_reporting_reassignment():
    init_db()
    with TestClient(app) as client:
        company = _create_company(client, "agent-management-tenant")
        company_id = company["id"]
        coordinator = _create_agent(
            client, company_id, "agent-management-tenant", "Nora", "Company coordination",
            title="Head of Agents", authority="COORDINATOR", seniority_level=9,
        )
        architect = _create_agent(
            client, company_id, "agent-management-tenant", "Kai", "Platform architecture",
            title="Platform Architect", manager_id=coordinator["id"], seniority_level=5,
        )
        child = _create_agent(
            client, company_id, "agent-management-tenant", "Rin", "Technical research",
            title="Technical Researcher", manager_id=architect["id"], seniority_level=2,
        )

        edit = client.patch(f"/v2/companies/{company_id}/agents/{architect['id']}", json={
            "tenant_id": "agent-management-tenant",
            "actor_id": "founder",
            "name": "Kai Tan",
            "role": "Cloud and platform architecture",
            "title": "Senior Platform Architect",
            "description": "Owns the platform blueprint and engineering standards",
            "skills": ["architecture", "cloud", "security"],
            "responsibilities": ["Design target architecture", "Review implementation risks"],
            "system_prompt": "You are Kai, a careful platform architect.",
            "seniority_level": 7,
            "authority": "SPECIALIST",
            "manager_id": coordinator["id"],
        })
        assert edit.status_code == 200, edit.text
        assert edit.json()["name"] == "Kai Tan"
        assert edit.json()["data"]["title"] == "Senior Platform Architect"
        assert edit.json()["data"]["skills"] == ["architecture", "cloud", "security"]

        promoted = client.post(
            f"/v2/companies/{company_id}/agents/{architect['id']}/promote",
            json={"tenant_id": "agent-management-tenant", "actor_id": "founder"},
        )
        assert promoted.status_code == 200, promoted.text
        assert promoted.json()["data"]["seniority_level"] == 8
        demoted = client.post(
            f"/v2/companies/{company_id}/agents/{architect['id']}/demote",
            json={"tenant_id": "agent-management-tenant", "actor_id": "founder"},
        )
        assert demoted.status_code == 200, demoted.text
        assert demoted.json()["data"]["seniority_level"] == 7

        removed = client.request("DELETE",
            f"/v2/companies/{company_id}/agents/{architect['id']}",
            json={"tenant_id": "agent-management-tenant", "actor_id": "founder"},
        )
        assert removed.status_code == 200, removed.text
        assert removed.json()["removed"] is True
        assert removed.json()["preserved_history"] is True
        assert removed.json()["agent"]["status"] == "ARCHIVED"

        graph = client.get(f"/v2/companies/{company_id}/graph?tenant_id=agent-management-tenant").json()
        archived = next(node for node in graph["nodes"] if node["id"] == architect["id"])
        assert archived["name"] == "Kai Tan"
        assert archived["status"] == "ARCHIVED"
        new_manager_line = next(
            edge for edge in graph["edges"]
            if edge["source"] == child["id"] and edge["relationship"] == "reports_to"
        )
        assert new_manager_line["target"] == coordinator["id"]
        verify = client.get(f"/v2/companies/{company_id}/events/verify?tenant_id=agent-management-tenant")
        assert verify.status_code == 200
        assert verify.json()["valid"] is True


def test_agent_management_rejects_duplicate_coordinators_and_reporting_cycles():
    init_db()
    with TestClient(app) as client:
        company = _create_company(client, "agent-governance-tenant")
        company_id = company["id"]
        first = _create_agent(
            client, company_id, "agent-governance-tenant", "Founder Delegate", "Company coordination",
            authority="COORDINATOR",
        )
        duplicate = client.post(f"/v2/companies/{company_id}/agents", json={
            "tenant_id": "agent-governance-tenant",
            "actor_id": "founder",
            "name": "Second Coordinator",
            "role": "Company coordination",
            "title": "Chief of Staff",
            "authority": "COORDINATOR",
        })
        assert duplicate.status_code == 422
        second = _create_agent(
            client, company_id, "agent-governance-tenant", "Team Lead", "Engineering leadership",
            title="Engineering Lead", manager_id=first["id"],
        )
        third = _create_agent(
            client, company_id, "agent-governance-tenant", "Engineer", "Systems engineering",
            title="Systems Engineer", manager_id=second["id"],
        )
        cycle = client.patch(f"/v2/companies/{company_id}/agents/{second['id']}", json={
            "tenant_id": "agent-governance-tenant",
            "actor_id": "founder",
            "manager_id": third["id"],
        })
        assert cycle.status_code == 422
        graph = client.get(f"/v2/companies/{company_id}/graph?tenant_id=agent-governance-tenant").json()
        assert sum(
            1 for node in graph["nodes"]
            if node["type"] == "agent" and node["status"] != "ARCHIVED"
            and node["data"].get("authority") == "COORDINATOR"
        ) == 1


def test_agent_cannot_be_removed_while_assigned_work_is_running():
    init_db()
    with TestClient(app) as client:
        company = _create_company(client, "agent-running-tenant")
        specialist = _create_agent(client, company["id"], "agent-running-tenant", "Build Agent", "Software delivery")
        work = _create_node(
            client, company["id"], "agent-running-tenant", "work", "Active implementation",
            {"assigned_agent_id": specialist["id"]},
        )
        from app.company_graph import update_node
        update_node(
            company_id=company["id"],
            tenant_id="agent-running-tenant",
            actor_id="founder",
            node_id=work["id"],
            status="RUNNING",
        )
        removed = client.request("DELETE",
            f"/v2/companies/{company['id']}/agents/{specialist['id']}",
            json={"tenant_id": "agent-running-tenant", "actor_id": "founder"},
        )
        assert removed.status_code == 409
        assert "work running" in removed.json()["detail"].lower()
