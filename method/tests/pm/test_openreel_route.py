"""PM hands off an OpenReel-only route without claiming an installed executor."""

from pm.agent_transport import AgentMessage


def test_request_persists_openreel_route_when_agent_is_unconfigured(client, projects_dir):
    # Given a project created through the production API.
    pid = client.post('/api/projects', json={
        'requirement': 'OpenMontage 流程演示', 'pipeline_type': 'screen-demo',
    }).json()['project_id']
    # When requesting production with no agent configuration.
    response = client.post(f'/api/projects/{pid}/run', json={'mode': 'local_technical_test'})
    # Then the immutable handoff selects OpenReel while remaining unavailable.
    assert response.status_code == 202
    assert response.json()['render_runtime'] == 'openreel'
    from pm.production_types import ProductionRequest
    stored = ProductionRequest.model_validate_json(
        (projects_dir / pid / 'production_request.json').read_text(encoding='utf-8')
    )
    assert stored.render_runtime == 'openreel'
    view = client.get(f'/api/projects/{pid}/production').json()
    assert view['status'] == 'awaiting_agent'
    assert view['consumer']['ready'] is False
    assert view['media_url'] is None


def test_transport_carries_openreel_constraint_when_dispatching():
    # Given the trusted local transport protocol.
    # When building an execution message.
    message = AgentMessage(protocol=1, operation='execute')
    # Then its serialized contract constrains the agent's renderer too.
    assert message.model_dump()['render_runtime'] == 'openreel'
    assert 'OpenReel' in message.instructions


def test_proposal_explains_openreel_availability_when_renderers_are_unconfigured(client):
    # Given an offline PM proposal with no production agent configured.
    # When a user asks for a project proposal.
    response = client.post('/api/chat/propose', json={'requirement': '制作流程演示'})
    # Then the user sees the chosen renderer and the remaining integration gap.
    body = response.json()
    assert 'OpenReel' in body['concept']
    assert '未接通' in body['note']
    assert body['is_offline_substitute'] is True


def test_web_cannot_override_openreel_route_when_submitting(client):
    # Given a managed project.
    pid = client.post('/api/projects', json={'requirement': 'route guard'}).json()['project_id']
    # When a web client tries to choose another renderer.
    response = client.post(f'/api/projects/{pid}/run', json={
        'mode': 'local_technical_test', 'render_runtime': 'remotion',
    })
    # Then the API rejects the untrusted override.
    assert response.status_code == 422
