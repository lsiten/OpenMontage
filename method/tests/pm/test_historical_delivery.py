"""Historical files are TEST DOUBLE fixtures, never evidence of a new production run."""

import hashlib
import json
import subprocess

import pytest

from pm.production import production_queue


@pytest.fixture
def historical_project(client, projects_dir):
    """A valid compose checkpoint without any request, queue, approvals or prior stages."""
    response = client.post('/api/projects', json={
        'requirement': 'TEST DOUBLE ONLY historical delivery boundary',
        'pipeline_type': 'screen-demo',
    })
    assert response.status_code == 201
    pid = response.json()['project_id']
    pdir = projects_dir / pid
    report = {'version': '1.0', 'outputs': [{
        'path': 'renders/final.mp4', 'format': 'mp4',
        'resolution': '1280x720', 'duration_seconds': 15,
    }]}
    (pdir / 'checkpoint_compose.json').write_text(json.dumps({
        'version': '1.0', 'project_id': pid, 'stage': 'compose',
        'status': 'completed', 'pipeline_type': 'screen-demo',
        'timestamp': '2026-10-26T14:20:00Z', 'artifacts': {'render_report': report},
    }), encoding='utf-8')
    return pid, pdir


@pytest.mark.parametrize('media', ['corrupt', 'valid', 'missing', 'no_checkpoint', 'tampered'])
def test_history_cannot_complete_or_download_without_queue(historical_project, client, media):
    # Given historical files, including either real local test media or known corruption.
    pid, pdir = historical_project
    video = pdir / 'renders/final.mp4'
    if media in ('valid', 'tampered'):
        subprocess.run([
            'ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=1280x720:r=24:d=1',
            '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(video),
        ], check=True)
        subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-f', 'null', '-'], check=True)
    if media in ('corrupt', 'no_checkpoint', 'tampered'):
        video.write_bytes(b'TEST DOUBLE NOT A REAL VIDEO!!')
    if media == 'no_checkpoint':
        (pdir / 'checkpoint_compose.json').unlink()
    before = {str(p.relative_to(pdir)): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in pdir.rglob('*') if p.is_file()}
    # When the observer and media route inspect the unverified historical project.
    view = client.get(f'/api/projects/{pid}/production')
    download = client.get(f'/api/projects/{pid}/media/final.mp4')
    # Then the shared guard rejects success/download while retaining every historical byte.
    assert view.status_code == 200
    assert view.json()['status'] == 'historical_unverified'
    assert '历史产物未核验' in view.json()['error']
    assert view.json()['request'] is None
    assert view.json()['media_url'] is None
    assert view.json()['history'] == []
    assert download.status_code == 404
    assert production_queue().get(pid) is None
    assert not (pdir / 'production_request.json').exists()
    assert {str(p.relative_to(pdir)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in pdir.rglob('*') if p.is_file()} == before


@pytest.mark.parametrize('field,value', [('project_id', 'another-project'),
                                        ('pipeline_type', 'cinematic')])
def test_foreign_history_never_grants_playback(historical_project, client, field, value):
    # Given a schema-valid checkpoint belonging to another project or pipeline.
    pid, pdir = historical_project
    path = pdir / 'checkpoint_compose.json'
    checkpoint = json.loads(path.read_text())
    checkpoint[field] = value
    path.write_text(json.dumps(checkpoint))
    (pdir / 'renders/final.mp4').write_bytes(b'TEST DOUBLE NOT A REAL VIDEO!!')
    # When querying both public boundaries.
    view = client.get(f'/api/projects/{pid}/production').json()
    download = client.get(f'/api/projects/{pid}/media/final.mp4')
    # Then the identity error is explicit and cannot expose media.
    assert view['status'] in ('failed', 'historical_unverified')
    assert view['error']
    assert view['media_url'] is None
    assert download.status_code == 404


def test_orphan_request_never_claims_a_persistent_handoff(client, projects_dir):
    # Given a request copied onto another project, with no queue entry there.
    first = client.post('/api/projects', json={'requirement': 'TEST DOUBLE source'}).json()['project_id']
    second = client.post('/api/projects', json={'requirement': 'TEST DOUBLE target'}).json()['project_id']
    request = client.post(f'/api/projects/{first}/run', json={'mode': 'local_technical_test'}).json()
    request['project_id'] = second
    (projects_dir / second / 'production_request.json').write_text(json.dumps(request))
    # When observing the copied request through HTTP.
    view = client.get(f'/api/projects/{second}/production').json()
    # Then the observer reports the missing durable queue, never an accepted job or video.
    assert view['status'] == 'failed'
    assert '持久队列' in view['error']
    assert view['media_url'] is None
    assert client.get(f'/api/projects/{second}/media/final.mp4').status_code == 404
