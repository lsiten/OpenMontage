"""Application-owned queue consumer; creative production stays in the real agent."""

from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from threading import Event
from typing import Callable
from jsonschema.exceptions import ValidationError as ArtifactValidationError

from pm.agent_transport import AgentConfig, AgentMessage, AgentReply, ProcessCall, ProcessHooks, TransportError, execute_local
from pm.production_evidence import EvidenceError, read_checkpoint, verify_delivery
from pm.production_queue import ProductionQueue, now
from pm.production_types import ConsumerState, QueueRecord

logger = logging.getLogger(__name__)


class Consumer:
    """Mutable service lifetime: one owned worker, joined on app shutdown."""

    def __init__(self, queue: ProductionQueue, config: AgentConfig | None,
                 project_exists: Callable[[str], bool]) -> None:
        self.queue = queue
        self.config = config
        self.project_exists = project_exists
        self.stop = Event()
        self.active_project_id: str | None = None
        self.next_probe_at = 0.0
        self.state = ConsumerState(configured=config is not None,
                                   test_double=config.test_double if config else False)

    def probe(self) -> bool:
        if self.config is None:
            return False
        try:
            execute_local(self.config.model_copy(update={'timeout_seconds': min(5, self.config.timeout_seconds)}),
                          ProcessCall(message=AgentMessage(protocol=1, operation='health')),
                          ProcessHooks(self.stop.is_set, lambda reply: None))
        except (OSError, ValueError, TransportError) as exc:
            logger.warning('consumer.unavailable', extra={'reason': str(exc)})
            self.state = ConsumerState(configured=True, checked_at=now(), error=str(exc),
                                       test_double=self.config.test_double)
            self.next_probe_at = time.monotonic() + 5
            return False
        self.state = ConsumerState(configured=True, ready=True, checked_at=now(), error=None,
                                   test_double=self.config.test_double)
        return True

    def run(self) -> None:
        """Service loop exists only within the application's structured lifespan."""
        try:
            self.probe()
            while not self.stop.is_set():
                self.consume_once()
                self.stop.wait(0.2)
        finally:
            self.state = self.state.model_copy(update={'ready': False, 'connected': False,
                                                       'error': '本地消费服务已停止'})

    def consume_once(self) -> bool:
        if self.config is None:
            return False
        if time.monotonic() < self.next_probe_at:
            return False
        for candidate in self.queue.candidates():
            pid = candidate.request.project_id
            if not self.project_exists(pid):
                continue
            with self.queue.lease(pid) as lease_fd:
                if lease_fd is None:
                    continue
                if not self.probe():
                    return False
                record = self.queue.claim(pid)
                if record is None:
                    continue
                self._consume(record, lease_fd)
                return True
        return False

    def _consume(self, record: QueueRecord, lease_fd: int) -> None:
        config = self.config
        if config is None:
            raise TransportError('本地入口未配置')
        request = record.request
        self.active_project_id = request.project_id
        pdir = self.queue.project_dir(request.project_id)

        def cancelled() -> bool:
            current = self.queue.get(request.project_id)
            return self.stop.is_set() or current is None or current.cancel_requested or not self.project_exists(request.project_id)

        def receive(reply: AgentReply) -> None:
            match reply.kind:
                case 'ready':
                    self.state = self.state.model_copy(update={'connected': True})
                case 'log':
                    self.queue.log(record, reply.message)
                case 'result':
                    return
                case unreachable:
                    from typing_extensions import assert_never
                    assert_never(unreachable)

        try:
            if request.mode not in config.allowed_modes:
                raise TransportError('制作模式尚未获本地管理员授权')
            stored = type(request).model_validate_json((pdir / 'production_request.json').read_text(encoding='utf-8'))
            if stored != request:
                raise TransportError('项目内请求与持久队列不匹配')
            reply = execute_local(config, ProcessCall(lease_fd=lease_fd,
                log_directory=pdir / 'agent-runs' / record.token, message=AgentMessage(
                protocol=1, operation='execute', project_id=request.project_id, request_id=request.request_id,
                attempt_token=record.token, mode=request.mode, projects_dir=str(self.queue.root),
                request_file=str(pdir / 'production_request.json'),
                render_runtime=request.render_runtime,
            )), ProcessHooks(cancelled, receive))
            self.state = self.state.model_copy(update={'connected': False})
            match reply.status:
                case 'completed':
                    proof = verify_delivery(request, pdir)
                    record = record.model_copy(update={'status': 'completed', **proof.model_dump()})
                case 'awaiting_human':
                    checkpoints = [read_checkpoint(p) for p in pdir.glob('checkpoint_*.json')]
                    if not any(c.status == 'awaiting_human' and c.project_id == request.project_id
                               and c.pipeline_type == request.pipeline_type
                               and c.metadata.request_id == request.request_id for c in checkpoints):
                        raise EvidenceError('消费端声称待审批，但没有同请求的 canonical 审批 checkpoint')
                    record = record.model_copy(update={'status': 'awaiting_human'})
                case 'failed' | 'cancelled':
                    record = record.model_copy(update={'status': reply.status, 'error': reply.message or '本地 agent 返回失败或取消'})
                case unreachable:
                    from typing_extensions import assert_never
                    assert_never(unreachable)
        except InterruptedError:
            record = record.model_copy(update={'status': 'awaiting_agent' if self.stop.is_set() else 'cancelled',
                                               'error': '服务关闭，保留历史等待恢复' if self.stop.is_set() else '请求已取消'})
        except (OSError, ValueError, KeyError, TransportError, EvidenceError, subprocess.SubprocessError, ArtifactValidationError) as exc:
            logger.warning('consumer.request_failed', extra={'project_id': request.project_id,
                           'request_id': request.request_id, 'reason': str(exc)})
            record = record.model_copy(update={'status': 'failed', 'error': str(exc)})
        finally:
            self.state = self.state.model_copy(update={'connected': False})
            self.active_project_id = None
        self.queue.finish(record)
