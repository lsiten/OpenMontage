"""Pinned, administrator-supplied local process transport. Never executes a web command."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path
from contextlib import contextmanager
from dataclasses import dataclass
from threading import Event
from typing import BinaryIO, Callable, Iterator, Literal

from pydantic import Field, model_validator

from lib.paths import REPO_ROOT
from pm.production_types import Mode, ProductionRequest, Record


class TransportError(RuntimeError):
    """A local process or its typed wire protocol failed."""


class AgentConfig(Record):
    executable: Path
    executable_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    args: tuple[str, ...] = ()
    allowed_modes: tuple[Mode, ...] = ('local_technical_test',)
    local_only: Literal[True]
    service_fee_usd: Literal[0]
    authorized: Literal[True]
    authorization_evidence: str = Field(min_length=1)
    license_evidence: str = Field(min_length=1)
    test_double: bool = False
    timeout_seconds: float = Field(default=600, gt=0, le=3600)

    @model_validator(mode='after')
    def local_executable(self) -> AgentConfig:
        if not self.executable.is_absolute() or self.executable.name in ('multica', 'multica.exe'):
            raise TransportError('入口必须为管理员指定的本地绝对路径，不能为平台 daemon')
        return self

    def verify(self) -> None:
        if hashlib.sha256(self.executable.read_bytes()).hexdigest() != self.executable_sha256:
            raise TransportError('本地入口内容哈希与授权配置不一致')


class AgentMessage(Record):
    protocol: Literal[1]
    operation: Literal['health', 'execute']
    project_id: str = ''
    request_id: str = ''
    attempt_token: str = ''
    mode: Mode = 'local_technical_test'
    projects_dir: str = ''
    request_file: str = ''
    render_runtime: Literal['openreel'] = 'openreel'
    instructions: str = (
        'Read AGENT_GUIDE.md, the request, manifest and stage director skills; discover the registry. '
        'This project requires OpenReel for editing, composition, rendering and export. '
        'This overrides legacy runtime suggestions in manifests/skills; never fall back to Remotion '
        'or require its installation. If the OpenReel execution bridge is unavailable, report failure '
        'with the missing prerequisite rather than claiming production success. '
        'Use lib.checkpoint.get_next_stage to resume. Only the agent makes creative decisions. '
        'Preserve manifest approval gates; never synthesize human_approved. No paid calls, credentials, '
        'model downloads, publishing or sensitive media. Write canonical artifacts/checkpoints in this '
        'project; checkpoint metadata.request_id must match. Return awaiting_human at an approval gate.'
    )


class AgentReply(Record):
    protocol: Literal[1]
    kind: Literal['ready', 'log', 'result']
    project_id: str = ''
    request_id: str = ''
    attempt_token: str = ''
    status: Literal['completed', 'awaiting_human', 'failed', 'cancelled'] = 'failed'
    message: str = Field(default='', max_length=4000)
    local_only: Literal[True] = True
    service_fee_usd: Literal[0] = 0
    test_double: bool = False


class ProcessCall(Record):
    message: AgentMessage
    # A live lease FD is intentionally inherited by the worker. It prevents
    # duplicate execution while a worker survives an abruptly killed PM process.
    lease_fd: int | None = None
    log_directory: Path | None = None


@dataclass(frozen=True, slots=True)
class ProcessHooks:
    cancelled: Callable[[], bool]
    received: Callable[[AgentReply], None]


@contextmanager
def capture_files(directory: Path | None) -> Iterator[tuple[BinaryIO, BinaryIO]]:
    if directory is None:
        with tempfile.TemporaryFile() as output, tempfile.TemporaryFile() as errors:
            yield output, errors
    else:
        directory.mkdir(parents=True, exist_ok=False)
        with (directory / 'stdout.jsonl').open('x+b') as output, (directory / 'stderr.log').open('x+b') as errors:
            yield output, errors


def execute_local(config: AgentConfig, call: ProcessCall, hooks: ProcessHooks) -> AgentReply:
    """Drain bounded NDJSON in real time and always reap this exact process group."""
    config.verify()
    # Deliberately omit inherited credentials/proxy/model configuration. This is
    # not an OS sandbox: only an audited, authorized local wrapper may be configured.
    env = {'PATH': '/usr/bin:/bin:/opt/homebrew/bin', 'LANG': 'en_US.UTF-8',
           'PYTHONUNBUFFERED': '1', 'OPENMONTAGE_PROJECTS_DIR': call.message.projects_dir}
    with capture_files(call.log_directory) as (output, errors):
        with subprocess.Popen([str(config.executable), *config.args], cwd=REPO_ROOT, env=env,
                              stdin=subprocess.PIPE, stdout=output, stderr=errors,
                              start_new_session=True,
                              pass_fds=(() if call.lease_fd is None else (call.lease_fd,))) as proc:
            deadline = time.monotonic() + config.timeout_seconds
            offset = 0
            terminal = None
            ready = False
            try:
                if proc.stdin is None:
                    raise TransportError('本地 agent 输入通道不可用')
                proc.stdin.write((call.message.model_dump_json() + '\n').encode())
                proc.stdin.close()
                while True:
                    if hooks.cancelled():
                        raise InterruptedError('本地消费已停止或取消')
                    if time.monotonic() > deadline:
                        raise TransportError('本地 agent 执行超时')
                    size = os.fstat(output.fileno()).st_size
                    if max(size, os.fstat(errors.fileno()).st_size) > 4 * 1024 * 1024:
                        raise TransportError('本地 agent 协议输出超出限制')
                    pending = os.pread(output.fileno(), size - offset, offset)
                    lines = pending.split(b'\n')
                    for line in lines[:-1]:
                        offset += len(line) + 1
                        reply = AgentReply.model_validate_json(line)
                        if reply.test_double != config.test_double:
                            raise TransportError('消费端 test_double 身份与配置不一致')
                        match reply.kind:
                            case 'ready':
                                if ready or terminal is not None:
                                    raise TransportError('消费端重复握手')
                                ready = True
                            case 'log' | 'result':
                                if not ready or terminal is not None:
                                    raise TransportError('消费端未握手或终态后仍输出')
                                if (reply.project_id, reply.request_id, reply.attempt_token) != (
                                    call.message.project_id, call.message.request_id, call.message.attempt_token
                                ):
                                    raise TransportError('消费端返回 project_id/request_id/租约不匹配')
                                if reply.kind == 'result':
                                    terminal = reply
                            case unreachable:
                                from typing_extensions import assert_never
                                assert_never(unreachable)
                        hooks.received(reply)
                    if proc.poll() is not None:
                        # A final drain is needed if the process exited during pread.
                        if os.fstat(output.fileno()).st_size > size:
                            continue
                        if lines[-1]:
                            raise TransportError('消费端协议行未结束')
                        break
                    Event().wait(0.03)
                if proc.returncode != 0:
                    raise TransportError(f'本地 agent 进程退出码 {proc.returncode}')
                if not ready:
                    raise TransportError('本地 agent 未返回就绪握手')
                if call.message.operation == 'health':
                    return AgentReply(protocol=1, kind='ready', test_double=config.test_double)
                if terminal is None:
                    raise TransportError('本地 agent 未返回请求终态')
                return terminal
            finally:
                # A dedicated session contains only this transport and its tools.
                # Signal the recorded process group, never a name or shared daemon.
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    proc.wait()
                except PermissionError:
                    # Darwin may reject signalling a group whose leader just
                    # exited. Reap it, or terminate only our recorded child.
                    if proc.poll() is None:
                        proc.terminate()
                try:
                    proc.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:
                        os.killpg(proc.pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        proc.kill()
                    proc.wait()
                if call.log_directory:
                    (call.log_directory / 'exit.json').write_text(json.dumps({
                        'pid': proc.pid, 'returncode': proc.returncode,
                        'project_id': call.message.project_id, 'request_id': call.message.request_id,
                        'attempt_token': call.message.attempt_token,
                    }), encoding='utf-8')
