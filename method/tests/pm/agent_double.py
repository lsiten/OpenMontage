"""TEST DOUBLE ONLY: protocol faults and a real awaiting-human checkpoint. No AI or approvals."""

import json
import sys
import time
from pathlib import Path

# This file is launched only by tests via a trusted, static configuration.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from lib.checkpoint import get_next_stage, write_checkpoint

message = json.loads(sys.stdin.readline())
scenario = sys.argv[1]


def emit(kind, **fields):
    print(json.dumps({'protocol': 1, 'kind': kind, 'test_double': True, **fields}), flush=True)


if scenario == 'unready':
    sys.exit(3)
emit('ready')
if message['operation'] == 'health':
    sys.exit(0)

identity = {key: message[key] for key in ('project_id', 'request_id', 'attempt_token')}
root = Path(message['projects_dir'])
project = root / message['project_id']
(project / 'double-started').write_text(str(__import__('os').getpid()))

if scenario == 'wait':
    emit('log', **identity, message='TEST DOUBLE: waiting for cancellation; no AI connected')
    time.sleep(30)
elif scenario == 'wrong-project':
    identity['project_id'] = 'another-project'
    emit('result', **identity, status='completed')
elif scenario == 'exit':
    emit('log', **identity, message='TEST DOUBLE: deterministic process failure')
    sys.exit(7)
elif scenario == 'malformed':
    print('not-json', flush=True)
elif scenario == 'no-video':
    emit('result', **identity, status='completed')
elif scenario == 'failed':
    emit('result', **identity, status='failed', message='TEST DOUBLE: tool failed')
else:
    next_stage = get_next_stage(root, message['project_id'], 'screen-demo')
    emit('log', **identity, message=f'TEST DOUBLE: get_next_stage={next_stage}; no real AI')
    brief = {
        'version': '1.0', 'title': 'TEST DOUBLE', 'hook': 'protocol fixture',
        'key_points': ['not a real production'], 'tone': 'technical', 'style': 'test',
        'target_platform': 'generic', 'target_duration_seconds': 15,
    }
    write_checkpoint(root, message['project_id'], 'idea', 'awaiting_human', {'brief': brief},
                     pipeline_type='screen-demo', metadata={'request_id': message['request_id']})
    emit('result', **identity, status='awaiting_human')
