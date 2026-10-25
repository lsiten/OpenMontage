"""Real OS/SQLite recovery tests. All executors here are labelled test doubles."""

import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from pm.consumer import Consumer
from pm.production import production_queue
from pm.production_queue import ProductionQueue
from pm.production_types import RequestControl
from tests.pm.test_consumer import create_request, double_config


def test_two_consumers_share_single_project_lease(client):
    # Given one submitted request and a TEST DOUBLE process holding its lease.
    pid, task = create_request(client)
    queue = production_queue()
    first = Consumer(queue, double_config('wait'), lambda _: True)
    second = Consumer(ProductionQueue(queue.root), double_config('gate'), lambda _: True)
    worker = threading.Thread(target=first.consume_once)
    worker.start()
    try:
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not (queue.project_dir(pid) / 'double-started').exists():
            threading.Event().wait(0.03)
        assert (queue.project_dir(pid) / 'double-started').is_file()
        # When an independent consumer tries to claim the same project.
        assert second.consume_once() is False
        # Then there is exactly one attempt and no second child execution.
        assert queue.get(pid).attempt == 1
        queue.control(pid, (RequestControl(request_id=task['request_id']), False))
    finally:
        first.stop.set()
        worker.join(timeout=10)
    assert not worker.is_alive()
    with queue.lease(pid) as fd:
        assert fd is not None


def test_crashed_parent_keeps_orphan_worker_fenced(client, tmp_path):
    # Given a request and a disposable parent that passes its lock to a test child.
    pid, task = create_request(client)
    queue = production_queue()
    receipt = tmp_path / 'child.json'
    release = tmp_path / 'release'
    parent_script = '''
import json, os, subprocess, sys
from pathlib import Path
from pm.production_queue import ProductionQueue
q = ProductionQueue(Path(sys.argv[1]))
with q.lease(sys.argv[2]) as fd:
    assert fd is not None
    q.claim(sys.argv[2])
    code = "import pathlib,sys,time; p=pathlib.Path(sys.argv[1]); deadline=time.monotonic()+5\\nwhile not p.exists() and time.monotonic()<deadline: time.sleep(.03)"
    child = subprocess.Popen([sys.executable, '-c', code, sys.argv[4]], pass_fds=(fd,),
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    Path(sys.argv[3]).write_text(json.dumps({'pid': child.pid}))
    os._exit(0)
'''
    # When the parent dies abruptly while the worker is still alive.
    subprocess.run([sys.executable, '-c', parent_script, str(queue.root), pid, str(receipt), str(release)], check=True)
    assert json.loads(receipt.read_text())['pid'] > 0
    try:
        with queue.lease(pid) as fd:
            assert fd is None
    finally:
        release.touch()
    # Then a restarted consumer waits for child exit before recovering this request.
    deadline = time.monotonic() + 8
    recovered = False
    while time.monotonic() < deadline:
        with queue.lease(pid) as fd:
            if fd is not None:
                recovered = True
                break
        threading.Event().wait(0.03)
    assert recovered
    consumer = Consumer(queue, double_config('gate'), lambda _: True)
    assert consumer.consume_once() is True
    assert queue.get(pid).attempt == 2
    assert queue.get(pid).status == 'awaiting_human'
    assert any(e.event == 'recovering' for e in queue.history(pid))


def test_explicit_retry_preserves_prior_failure(client):
    # Given an actual failed local TEST DOUBLE execution.
    pid, task = create_request(client)
    queue = production_queue()
    assert Consumer(queue, double_config('failed'), lambda _: True).consume_once()
    assert queue.get(pid).status == 'failed'
    # When explicitly retrying the same request through the HTTP boundary.
    response = client.post(f'/api/projects/{pid}/run/retry', json={'request_id': task['request_id']})
    assert response.status_code == 200
    assert Consumer(queue, double_config('gate'), lambda _: True).consume_once()
    # Then history retains the failure and the request identity while the next attempt waits at approval.
    record = queue.get(pid)
    assert record.request.request_id == task['request_id']
    assert record.attempt == 2
    assert record.status == 'awaiting_human'
    events = queue.history(pid)
    assert any(e.event == 'failed' and e.message == 'TEST DOUBLE: tool failed' for e in events)
    assert any(e.event == 'retry_requested' for e in events)
