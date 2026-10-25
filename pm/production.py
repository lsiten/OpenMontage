"""Persist agent handoffs and observe canonical pipeline files; no executor."""

from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Final, Literal

from pydantic import BaseModel, ConfigDict, Field

from lib.pipeline_loader import load_pipeline_readonly
from pm import state

_REQUEST_LOCK: Final = threading.Lock()


class ProductionInput(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid')
    mode: Literal['local_technical_test', 'agent_production']


class TestSpec(BaseModel):
    model_config = ConfigDict(frozen=True)
    duration_seconds: int = 15
    width: int = 1280
    height: int = 720
    fps: int = 24
    shots: int = 3


class ProductionRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str
    project_id: str
    mode: Literal['local_technical_test', 'agent_production']
    pipeline_type: str
    manifest: str
    director_skills: list[str]
    status: Literal['awaiting_agent'] = 'awaiting_agent'
    agent_connected: Literal[False] = False
    created_at: str
    spec: TestSpec | None = None
    note: str = '制作任务已保存；本地 agent 执行通道未接入，尚未开始制作。'


class ProductionView(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    request: ProductionRequest | None = None
    status: str = 'not_requested'
    agent_connected: Literal[False] = False
    error: str | None = None
    log: str = ''
    media_url: str | None = None
    artifact_names: list[str] = Field(default_factory=list)


def request_production(project_id: str, pipeline_type: str, req: ProductionInput) -> ProductionRequest:
    """Reuse the manifest's stage contract; preserve one request per project."""
    with _REQUEST_LOCK:
        path = state._project_dir(project_id) / 'production_request.json'
        if path.is_file():
            return ProductionRequest.model_validate_json(path.read_text(encoding='utf-8'))
        manifest = load_pipeline_readonly(pipeline_type)
        task = ProductionRequest(
            request_id=uuid.uuid4().hex,
            project_id=project_id,
            mode=req.mode,
            pipeline_type=pipeline_type,
            manifest=f'pipeline_defs/{pipeline_type}.yaml',
            director_skills=[s['skill'] for s in manifest['stages'] if s.get('skill')],
            created_at=datetime.now(timezone.utc).isoformat(),
            spec=TestSpec() if req.mode == 'local_technical_test' else None,
        )
        tmp = path.with_suffix('.tmp')
        tmp.write_text(task.model_dump_json(indent=2), encoding='utf-8')
        tmp.replace(path)
        return task


def observe_production(project_id: str) -> ProductionView:
    """Report actual disk checkpoints. A queued task alone is never running."""
    pdir = state._project_dir(project_id)
    request_path = pdir / 'production_request.json'
    req = None
    error = None
    try:
        if request_path.is_file():
            req = ProductionRequest.model_validate_json(request_path.read_text(encoding='utf-8'))
    except (OSError, ValueError) as exc:
        error = f'制作任务无法读取：{exc}'
    artifact_names = sorted(p.stem for p in (pdir / 'artifacts').glob('*.json'))
    status = req.status if req else 'not_requested'
    if any(pdir.glob('checkpoint_*.json')):
        status = 'in_progress'
    video = pdir / 'renders/final.mp4'
    compose = pdir / 'checkpoint_compose.json'
    try:
        for stage_path in sorted(pdir.glob('checkpoint_*.json')):
            from lib.checkpoint import validate_checkpoint
            stage = json.loads(stage_path.read_text(encoding='utf-8'))
            validate_checkpoint(stage)
            if stage['project_id'] != project_id:
                status, error = 'failed', '阶段 checkpoint 的 project_id 与 PM 项目不一致'
            if stage['status'] == 'failed':
                status, error = 'failed', stage.get('error') or '制作阶段失败'
        if compose.is_file():
            from lib.checkpoint import validate_checkpoint
            checkpoint = json.loads(compose.read_text(encoding='utf-8'))
            validate_checkpoint(checkpoint)
            if checkpoint['project_id'] != project_id:
                status, error = 'failed', 'checkpoint 的 project_id 与 PM 项目不一致'
            else:
                status = checkpoint['status']
                error = checkpoint.get('error') or error
                if status == 'completed' and not video.is_file():
                    status, error = 'failed', '渲染报告已完成，但成片文件缺失'
    except (OSError, ValueError) as exc:
        status, error = 'failed', f'制作状态无法读取：{exc}'
    if error is not None:
        status = 'failed'
    log_path = pdir / 'production.log'
    log = log_path.read_text(encoding='utf-8', errors='replace')[-16000:] if log_path.is_file() else ''
    return ProductionView(
        project_id=project_id, request=req, status=status, error=error,
        log=log, artifact_names=artifact_names,
        media_url=f'/api/projects/{project_id}/media/final.mp4' if status == 'completed' and error is None else None,
    )
