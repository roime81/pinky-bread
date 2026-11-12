import base64
from pathlib import Path
from fastapi.testclient import TestClient

from app.main import app, registry
from app.database import init_db


def setup_module():
    init_db()
    registry.reload()


def test_agents_endpoint():
    with TestClient(app) as client:
        response = client.get('/v1/agents')
        assert response.status_code == 200
        ids = {a['agent_metadata']['agent_id'] for a in response.json()['agents']}
        assert {'airline_ops_agent', 'banking_refund_agent', 'general_assistant_agent'} <= ids


def test_cancelled_flight_pauses_for_approval():
    with TestClient(app) as client:
        response = client.post('/v1/workflows/invoke', json={
            'tenant_id': 'test-tenant',
            'user_id': 'test-user',
            'prompt': 'Review a cancelled flight and prepare a refund proposal for RM450.00.'
        })
        assert response.status_code == 200, response.text
        body = response.json()
        assert body['status'] == 'PENDING_APPROVAL'
        assert body['requires_human_approval'] is True
        assert body['pending_action']['amount'] == 450.0
        assert body['executed_agents'] == ['airline_ops_agent', 'banking_refund_agent']

        approval = client.post(f"/v1/workflows/{body['thread_id']}/approve", json={
            'approver_id': 'test-approver',
            'decision': 'APPROVED',
            'notes': 'approved for simulation'
        })
        assert approval.status_code == 200, approval.text
        final = approval.json()
        assert final['status'] == 'COMPLETED'
        assert final['tool_result']['result'] == 'SIMULATED_CREDIT_POSTED'
        assert final['tool_result']['environment'] == 'MVP_SIMULATION_ONLY'


def test_rejection_never_calls_tool():
    with TestClient(app) as client:
        response = client.post('/v1/workflows/invoke', json={'prompt': 'My airline flight was cancelled, please process refund RM120.'})
        body = response.json()
        assert body['status'] == 'PENDING_APPROVAL'
        approval = client.post(f"/v1/workflows/{body['thread_id']}/approve", json={
            'approver_id': 'risk-reviewer', 'decision': 'REJECTED', 'notes': 'insufficient evidence'
        })
        assert approval.json()['status'] == 'REJECTED'
        assert approval.json()['tool_result'] is None


def test_general_prompt_completes_without_approval():
    with TestClient(app) as client:
        response = client.post('/v1/workflows/invoke', json={'prompt': 'Explain the purpose of an enterprise AI agent registry.'})
        assert response.status_code == 200
        assert response.json()['status'] == 'COMPLETED'
        assert response.json()['requires_human_approval'] is False


def test_privacy_scrubber_masks_nric_and_email():
    from app.privacy import scrub_text
    result = scrub_text('Customer NRIC 810101-01-1234 and email person@example.com')
    assert '810101-01-1234' not in result.text
    assert 'person@example.com' not in result.text
    assert '<NRIC_1>' in result.text
    assert '<EMAIL_2>' in result.text
