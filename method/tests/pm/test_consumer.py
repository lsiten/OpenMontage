"""Local subprocess TEST DOUBLE contract tests; never evidence of real AI production."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import threading
import time

import pytest
from starlette.testclient import TestClient

from pm.agent_transport import AgentConfig
from pm.consumer import Consumer
from pm.production import observe_production, production_queue, request_production
from pm.production_queue import ProductionQueue, RequestConflict
from pm.production_types import ProductionInput, RequestControl
from pm.server import create_app


def double_config(scenario='gate', **changes):
    """Only static, developer-owned code is given to the process adapter."""
    return AgentConfig(
        executable=Path(sys.executable), executable_sha256=hashlib.sha256(Path(sys.executable).read_bytes()).hexdigest(),
        args=(str(Path(__file__).with_name('agent_double.py')), scenario),
        local_only=True, service_fee_usd=0, authorized=True, test_double=True,
        authorization_evidence='TEST DOUBLE fixture only; not real service authorization',
        license_evidence='Self-authored test fixture', **changes,
    )


def create_request(client):
    pid = client.post('/api/projects', json={'requirement': 'TEST DOUBLE ONLY', 'pipeline_type': 'screen-demo'}).json()['project_id']
    task = client.post(f'/api/projects/{pid}/run', json={'mode': 'local_technical_test'}).json()
    return pid, task


def await_state(client, pid, statuses):
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        view = client.get(f'/api/projects/{pid}/production').json()
        if view['status'] in statuses:
            return view
        threading.Event().wait(0.03)
    pytest.fail(f'consumer did not reach {statuses}: {view}')


def test_unconfigured_cannot_complete_from_stale_files(client, projects_dir):
    # Given an unconfigured service and a queued request.
    pid, task = create_request(client)
    (projects_dir / pid / 'renders/final.mp4').write_bytes(b'old video')
    # When observing the request.
    view = client.get(f'/api/projects/{pid}/production').json()
    # Then the file alone cannot produce success or a connection claim.
    assert view['status'] == 'awaiting_agent'
    assert view['agent_connected'] is False
    assert view['consumer']['ready'] is False
    assert '未配置' in view['error']
    assert view['media_url'] is None
    assert client.get(f'/api/projects/{pid}/media/final.mp4').status_code == 404


def test_concurrent_submissions_and_request_identity(client):
    # Given one managed project.
    pid, task = create_request(client)
    # When many independent SQLite connections submit the same request.
    with ThreadPoolExecutor(max_workers=8) as pool:
        tasks = list(pool.map(lambda _: request_production(pid, 'screen-demo', ProductionInput(mode='local_technical_test')), range(16)))
    # Then every submission returns the original identity.
    assert {r.request_id for r in tasks} == {task['request_id']}
    assert len([e for e in production_queue().history(pid) if e.event == 'requested']) == 1
    assert client.post(f'/api/projects/{pid}/run', json={'mode': 'local_technical_test', 'request_id': 'different'}).status_code == 409


@pytest.mark.parametrize('field,value', [('executable', '/bin/sh'), ('shell', 'echo x'), ('endpoint', 'https://example.com'), ('path', '/tmp')])
def test_web_cannot_choose_transport(client, field, value):
    # Given a managed project.
    pid, _ = create_request(client)
    # When a web client tries to supply execution configuration.
    response = client.post(f'/api/projects/{pid}/run', json={'mode': 'local_technical_test', field: value})
    # Then the strict request schema refuses it.
    assert response.status_code == 422


def test_request_key_cannot_be_reused_across_projects(client):
    # Given a key already owned by one project.
    first = client.post('/api/projects', json={'requirement': 'first'}).json()['project_id']
    second = client.post('/api/projects', json={'requirement': 'second'}).json()['project_id']
    body = {'mode': 'local_technical_test', 'request_id': 'stable-key'}
    assert client.post(f'/api/projects/{first}/run', json=body).status_code == 202
    # When the same key is used for a different project.
    response = client.post(f'/api/projects/{second}/run', json=body)
    # Then the association fails closed.
    assert response.status_code == 409


def test_automatic_test_double_stops_at_real_manifest_gate(client, projects_dir):
    # Given a configured TEST DOUBLE subprocess, no author consumes requests manually.
    with TestClient(create_app(double_config())) as app_client:
        # When the HTTP client submits a new isolated request.
        pid, task = create_request(app_client)
        view = await_state(app_client, pid, {'awaiting_human', 'failed'})
    # Then the automatic consumer reaches the manifest gate without approving it.
    assert view['status'] == 'awaiting_human', view
    assert view['consumer']['test_double'] is True
    assert view['agent_connected'] is False  # finite child has exited
    assert view['media_url'] is None
    checkpoint = json.loads((projects_dir / pid / 'checkpoint_idea.json').read_text())
    assert checkpoint['human_approved'] is False
    assert checkpoint['metadata']['request_id'] == task['request_id']
    assert [e['event'] for e in view['history']].count('claimed') == 1
    assert 'get_next_stage=idea' in view['log']
    assert len(view['log'].splitlines()) >= 3


@pytest.mark.parametrize('scenario,error', [
    ('exit', '退出码 7'), ('wrong-project', '不匹配'), ('malformed', 'Invalid JSON'),
    ('failed', 'TEST DOUBLE: tool failed'), ('no-video', 'checkpoint_idea.json'),
])
def test_consumer_faults_never_show_success(client, scenario, error):
    # Given a local TEST DOUBLE with a deterministic wire/process/delivery failure.
    with TestClient(create_app(double_config(scenario))) as app_client:
        # When submitted through the same API as the web UI.
        pid, _ = create_request(app_client)
        view = await_state(app_client, pid, {'failed'})
    # Then the durable failure is visible and no media can be served.
    assert error in view['error']
    assert view['media_url'] is None
    assert view['agent_connected'] is False
    assert any(e['event'] == 'failed' for e in view['history'])


def test_live_cancel_releases_lease_and_preserves_logs(client):
    # Given a TEST DOUBLE process holding a project lease.
    with TestClient(create_app(double_config('wait'))) as app_client:
        pid, task = create_request(app_client)
        queue = production_queue()
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not app_client.get(f'/api/projects/{pid}/production').json()['agent_connected']:
            threading.Event().wait(0.03)
        with queue.lease(pid) as fd:
            assert fd is None
        # When cancellation targets this exact request.
        assert app_client.post(f'/api/projects/{pid}/run/cancel', json={'request_id': task['request_id']}).status_code == 200
        view = await_state(app_client, pid, {'cancelled'})
    # Then the process is reaped, the OS lease is free, and history survives reopen.
    with ProductionQueue(queue.root).lease(pid) as fd:
        assert fd is not None
    assert view['media_url'] is None
    assert any(e.event == 'cancel_requested' for e in queue.history(pid))


def test_shutdown_restart_and_retry_preserve_attempts(client):
    # Given a running TEST DOUBLE and an application shutdown.
    with TestClient(create_app(double_config('wait'))) as app_client:
        pid, task = create_request(app_client)
        await_state(app_client, pid, {'in_progress'})
    assert production_queue().get(pid).status == 'awaiting_agent'
    # When restarted with a gate-capable TEST DOUBLE.
    with TestClient(create_app(double_config())) as app_client:
        view = await_state(app_client, pid, {'awaiting_human', 'failed'})
    # Then request identity and the interruption history survive.
    assert view['status'] == 'awaiting_human', view
    assert view['request']['request_id'] == task['request_id']
    assert production_queue().get(pid).attempt == 2
    assert any('服务关闭' in e.message for e in production_queue().history(pid))


def test_unready_is_real_health_failure_not_connected(client):
    # Given a configured but unhealthy TEST DOUBLE.
    with TestClient(create_app(double_config('unready'))) as app_client:
        # When queued and health probing fails.
        pid, _ = create_request(app_client)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            view = app_client.get(f'/api/projects/{pid}/production').json()
            if view['consumer']['checked_at']:
                break
            threading.Event().wait(0.03)
    # Then configuration is not mistaken for readiness and no lease was claimed.
    assert view['consumer']['ready'] is False
    assert view['agent_connected'] is False
    assert view['media_url'] is None
    assert production_queue().get(pid).attempt == 0
