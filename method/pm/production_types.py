"""Typed request, transport and queue records; no production decisions."""

from __future__ import annotations

from typing import Literal
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

Mode = Literal['local_technical_test', 'agent_production']
RunStatus = Literal['awaiting_agent', 'in_progress', 'awaiting_human', 'completed', 'failed', 'cancelled']


class Record(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')


class ProductionInput(Record):
    mode: Mode
    request_id: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9_-]{1,80}$')


class RequestControl(Record):
    request_id: str = Field(pattern=r'^[a-zA-Z0-9_-]{1,80}$')


class TestSpec(Record):
    duration_seconds: int = 15
    width: int = 1280
    height: int = 720
    fps: int = 24
    shots: int = 3


class ProductionRequest(Record):
    request_id: str
    project_id: str
    mode: Mode
    pipeline_type: str
    manifest: str
    director_skills: list[str]
    render_runtime: Literal['openreel'] = 'openreel'
    status: Literal['awaiting_agent'] = 'awaiting_agent'
    agent_connected: Literal[False] = False
    created_at: str
    spec: TestSpec | None = None
    note: str = '制作请求已保存；以实际消费端连接与阶段记录为准。'


class QueueRecord(Record):
    request: ProductionRequest
    status: RunStatus = 'awaiting_agent'
    attempt: int = 0
    token: str = ''
    cancel_requested: bool = False
    error: str | None = None
    media_sha256: str | None = None
    evidence_sha256: str | None = None

    def event(self, event: str, message: str) -> QueueEvent:
        return QueueEvent(project_id=self.request.project_id, request_id=self.request.request_id,
                          attempt=self.attempt, timestamp=datetime.now(timezone.utc).isoformat(),
                          event=event, message=message)


class QueueEvent(Record):
    project_id: str
    request_id: str
    attempt: int
    timestamp: str
    event: str
    message: str


class ConsumerState(Record):
    configured: bool = False
    ready: bool = False
    connected: bool = False
    test_double: bool = False
    checked_at: str | None = None
    error: str | None = '未配置已授权的本地 agent 入口，尚未开始自动制作。'


class ProductionView(Record):
    project_id: str
    request: ProductionRequest | None = None
    status: str = 'not_requested'
    agent_connected: bool = False
    consumer: ConsumerState = Field(default_factory=ConsumerState)
    error: str | None = None
    log: str = ''
    media_url: str | None = None
    artifact_names: list[str] = Field(default_factory=list)
    history: list[QueueEvent] = Field(default_factory=list)
