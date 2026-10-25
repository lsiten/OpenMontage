"""Regressions for the LSIT-284 acceptance return; all data is isolated."""

def test_soft_delete_restores_metadata_and_media(client, projects_dir):
    # Given a managed project with a local media file.
    pid = client.post('/api/projects', json={'requirement': 'restore demo'}).json()['project_id']
    media = projects_dir / pid / 'assets/video/source.mp4'
    media.write_bytes(b'isolated test media')
    # When removed from the active library.
    assert client.delete(f'/api/project/{pid}').status_code == 204
    # Then the data is retained and an explicit restore recovers the project.
    assert client.get(f'/api/projects/{pid}').status_code == 404
    assert all(p['project_id'] != pid for p in client.get('/api/projects').json())
    assert client.get('/api/trash').json()[0]['project_id'] == pid
    assert media.read_bytes() == b'isolated test media'
    assert client.post(f'/api/projects/{pid}/restore').status_code == 200
    assert client.get(f'/api/projects/{pid}').json()['pm']['requirement'] == 'restore demo'


def test_identical_requirements_create_distinct_projects(client):
    # Given the same Chinese requirement submitted twice.
    body = {'requirement': '介绍本地视频制作流程'}
    # When creating two independent projects.
    first = client.post('/api/projects', json=body).json()
    second = client.post('/api/projects', json=body).json()
    # Then neither record overwrites the other.
    assert first['project_id'] != second['project_id']
    assert len(client.get('/api/projects').json()) == 2


def test_edit_title_status_budget_survive_new_db_connection(client, tmp_path):
    # Given a new managed project.
    pid = client.post('/api/projects', json={'requirement': 'edit demo'}).json()['project_id']
    # When editing the three user-facing management fields.
    response = client.put(f'/api/projects/{pid}', json={
        'title': '已编辑标题', 'status': 'in_progress', 'cost_budget_usd': 0,
    })
    # Then both the library and a reopened SQLite store contain the values.
    assert response.status_code == 200
    assert client.get('/api/projects').json()[0]['title'] == '已编辑标题'
    from pm.store import PMDatabase
    db = PMDatabase(tmp_path / 'pm.db')
    try:
        p = db.get_project(pid)
        assert (p.title, p.status, p.cost_budget_usd) == ('已编辑标题', 'in_progress', 0)
    finally:
        db.close()


def test_production_request_is_honest_manifest_handoff(client, projects_dir):
    # Given a project that has not been produced by an agent.
    pid = client.post('/api/projects', json={
        'requirement': 'OpenMontage 流程演示', 'pipeline_type': 'screen-demo',
    }).json()['project_id']
    # When explicitly requesting the approved local technical test.
    r = client.post(f'/api/projects/{pid}/run', json={'mode': 'local_technical_test'})
    # Then it is a persisted handoff, never a fake running/completed pipeline.
    assert r.status_code == 202
    task = r.json()
    assert task['project_id'] == pid
    assert task['status'] == 'awaiting_agent'
    assert task['agent_connected'] is False
    assert task['spec'] == {'duration_seconds': 15, 'width': 1280, 'height': 720, 'fps': 24, 'shots': 3}
    assert (projects_dir / pid / 'production_request.json').is_file()
    assert client.post(f'/api/projects/{pid}/run', json={'mode': 'local_technical_test'}).json()['request_id'] == task['request_id']


def test_unknown_status_cost_and_media_are_not_success(client):
    # Given an unknown project ID.
    # When querying all detail subresources.
    for suffix in ('status', 'cost', 'production', 'media/final.mp4'):
        # Then no empty success or arbitrary file response is returned.
        assert client.get(f'/api/projects/missing/{suffix}').status_code == 404


def test_failed_stage_is_visible_and_has_no_playback(client, projects_dir):
    # Given a real failed stage checkpoint in an isolated project.
    from lib.checkpoint import write_checkpoint
    pid = client.post('/api/projects', json={
        'requirement': 'failure test', 'pipeline_type': 'screen-demo',
    }).json()['project_id']
    write_checkpoint(projects_dir, pid, 'assets', 'failed', {},
                     pipeline_type='screen-demo', error='isolated media failure')
    # When the observer refreshes.
    body = client.get(f'/api/projects/{pid}/production').json()
    # Then it exposes the real failure and never offers a fake movie.
    assert body['status'] == 'failed'
    assert body['error'] == 'isolated media failure'
    assert body['media_url'] is None
