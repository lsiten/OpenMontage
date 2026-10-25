"""Delivery-boundary tests use a synthetic ungated manifest, never forged approvals."""

import json
import subprocess

import pytest

from pm import production_evidence
from pm.production import observe_production, production_queue
from pm.production_evidence import EvidenceError, verify_delivery
from tests.pm.test_consumer import create_request


@pytest.fixture
def delivery(client, projects_dir, monkeypatch):
    """TEST DOUBLE manifest narrows this unit test to compose; no production gate is bypassed."""
    pid, task = create_request(client)
    queue = production_queue()
    pdir = projects_dir / pid
    request = queue.get(pid).request
    video = pdir / 'renders/final.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=blue:s=1280x720:r=24:d=15',
                    '-c:v', 'libx264', '-preset', 'ultrafast', '-pix_fmt', 'yuv420p', str(video)], check=True)
    report = {'version': '1.0', 'outputs': [{'path': 'renders/final.mp4', 'format': 'mp4',
              'resolution': '1280x720', 'duration_seconds': 15}]}
    review = {'version': '1.0', 'output_path': 'renders/final.mp4', 'status': 'pass',
              'checks': {k: {} for k in ('technical_probe', 'visual_spotcheck', 'audio_spotcheck',
                                        'promise_preservation', 'subtitle_check')}}
    # Self-authored validation fixtures, not a claim that a real agent reviewed a movie.
    (pdir / 'artifacts/render_report.json').write_text(json.dumps(report))
    (pdir / 'artifacts/final_review.json').write_text(json.dumps(review))
    (pdir / 'artifacts/scene_plan.json').write_text(json.dumps({'scenes': [{}, {}, {}]}))
    # A raw schema fixture, not execution of screen-demo. The positive test uses
    # only the synthetic manifest below; the real-manifest test must reject it.
    (pdir / 'checkpoint_compose.json').write_text(json.dumps({
        'version': '1.0', 'project_id': pid, 'stage': 'compose', 'status': 'completed',
        'pipeline_type': 'screen-demo', 'timestamp': '2026-10-25T13:00:00Z',
        'artifacts': {'render_report': report}, 'metadata': {'request_id': task['request_id']},
    }))
    monkeypatch.setattr(production_evidence, 'load_pipeline_readonly',
                        lambda _: {'stages': [{'name': 'compose', 'human_approval_default': False}]})
    return pid, request, pdir


def test_verified_delivery_is_project_scoped_and_detects_tampering(delivery):
    # Given a real self-authored 15s/24fps file and synthetic compose-only evidence.
    pid, request, pdir = delivery
    queue = production_queue()
    proof = verify_delivery(request, pdir)
    with queue.lease(pid) as fd:
        assert fd is not None
        record = queue.claim(pid)
        queue.finish(record.model_copy(update={'status': 'completed', **proof.model_dump()}))
    assert observe_production(pid).media_url == f'/api/projects/{pid}/media/final.mp4'
    # When a validated artifact is changed after completion.
    (pdir / 'artifacts/final_review.json').write_text('{}')
    # Then playback fails closed despite the previous success and existing movie.
    view = observe_production(pid)
    assert view.status == 'failed'
    assert view.media_url is None
    assert '证据哈希' in view.error


def test_missing_video_never_validates(delivery):
    # Given canonical compose evidence, but no final file.
    pid, request, pdir = delivery
    (pdir / 'renders/final.mp4').rename(pdir / 'renders/retained.mp4')
    # When the worker claims completion.
    with pytest.raises(EvidenceError, match='缺失'):
        verify_delivery(request, pdir)
    # Then no hash or success can be returned.


def test_mismatched_checkpoint_request_never_validates(delivery):
    # Given a checkpoint copied from another request.
    pid, request, pdir = delivery
    path = pdir / 'checkpoint_compose.json'
    checkpoint = json.loads(path.read_text())
    checkpoint['metadata']['request_id'] = 'another-request'
    path.write_text(json.dumps(checkpoint))
    # When the worker claims completion.
    with pytest.raises(EvidenceError, match='不一致'):
        verify_delivery(request, pdir)
    # Then another request's evidence is rejected.


def test_original_manifest_still_requires_prior_gates(delivery, monkeypatch):
    # Given only compose evidence and the original screen-demo manifest.
    pid, request, pdir = delivery
    from lib.pipeline_loader import load_pipeline_readonly
    monkeypatch.setattr(production_evidence, 'load_pipeline_readonly', load_pipeline_readonly)
    # When the worker claims a complete original pipeline.
    with pytest.raises(FileNotFoundError, match='checkpoint_idea'):
        verify_delivery(request, pdir)
    # Then a compose-only TEST DOUBLE cannot pass real production validation.


def test_request_file_project_mismatch_is_visible(client, projects_dir):
    # Given an immutable queued request whose disk copy was changed.
    pid, task = create_request(client)
    path = projects_dir / pid / 'production_request.json'
    task['project_id'] = 'another-project'
    path.write_text(json.dumps(task))
    # When querying through the real HTTP observer.
    view = client.get(f'/api/projects/{pid}/production').json()
    # Then it is a failure without playback, not a fake queued/success state.
    assert view['status'] == 'failed'
    assert '不一致' in view['error']
    assert view['media_url'] is None
