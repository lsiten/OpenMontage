"""Persist agent handoffs and observe canonical evidence; no creative executor."""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from lib.pipeline_loader import load_pipeline_readonly
from pm import state
from pm.production_evidence import EvidenceError, evidence_digest, read_checkpoint
from pm.production_queue import ProductionQueue
from pm.production_types import (
    ConsumerState, ProductionInput, ProductionRequest, ProductionView, TestSpec,
)


def production_queue() -> ProductionQueue:
    return ProductionQueue(state.PROJECTS_DIR)


def request_production(project_id: str, pipeline_type: str, req: ProductionInput) -> ProductionRequest:
    """Resolve manifest metadata and transactionally deduplicate the project handoff."""
    manifest = load_pipeline_readonly(pipeline_type)
    task = ProductionRequest(
        request_id=req.request_id or uuid.uuid4().hex, project_id=project_id,
        mode=req.mode, pipeline_type=pipeline_type,
        manifest=f'pipeline_defs/{pipeline_type}.yaml',
        director_skills=[s['skill'] for s in manifest['stages'] if s.get('skill')],
        created_at=datetime.now(timezone.utc).isoformat(),
        spec=TestSpec() if req.mode == 'local_technical_test' else None,
    )
    return production_queue().register(task, req.request_id)


def observe_production(project_id: str, consumer: ConsumerState | None = None) -> ProductionView:
    """Queue state is authoritative for consumption; files alone cannot complete a queued job."""
    queue = production_queue()
    pdir = queue.project_dir(project_id)
    request_path = pdir / 'production_request.json'
    req = None
    error = None
    invalid_request = False
    record = queue.get(project_id)
    service = consumer or ConsumerState()
    try:
        if request_path.is_file():
            req = ProductionRequest.model_validate_json(request_path.read_text(encoding='utf-8'))
            if req.project_id != project_id or (record and record.request != req):
                error = '制作请求与 PM project_id 或持久队列不一致'
                invalid_request = True
            elif record is None:
                error, invalid_request = '制作请求缺少对应的持久队列记录', True
        elif record:
            error, invalid_request = '持久队列对应的制作请求文件缺失', True
    except (OSError, ValueError, EvidenceError) as exc:
        error = f'制作任务无法读取：{exc}'
        invalid_request = True
    artifact_names = sorted(p.stem for p in (pdir / 'artifacts').glob('*.json'))
    status = record.status if record else (req.status if req else 'not_requested')
    if record:
        error = record.error or error
    try:
        checkpoints = [read_checkpoint(p) for p in sorted(pdir.glob('checkpoint_*.json'))]
        for checkpoint in checkpoints:
            if checkpoint.project_id != project_id or (req and checkpoint.pipeline_type != req.pipeline_type):
                error = '阶段 checkpoint 的 project_id 或 pipeline 与 PM 项目不一致'
            if checkpoint.status == 'failed' and (record is None or record.status in ('failed', 'completed', 'awaiting_human')):
                error = checkpoint.error or '制作阶段失败'
        if record is None and (checkpoints or artifact_names or (pdir / 'renders/final.mp4').exists()):
            status = 'historical_unverified'
        if status == 'completed':
            video = pdir / 'renders/final.mp4'
            if not video.is_file() or not video.stat().st_size or not video.resolve().is_relative_to(pdir.resolve()):
                error = '渲染报告已完成，但成片文件缺失或位置无效'
            elif record and record.media_sha256 != hashlib.sha256(video.read_bytes()).hexdigest():
                error = '成片与消费端验证的文件哈希不一致'
            if record and record.evidence_sha256 != evidence_digest(pdir):
                error = '阶段或产物与消费端验证的证据哈希不一致'
            if record and not any(c.stage == 'compose' and c.status == 'completed'
                                  and c.metadata.request_id == record.request.request_id for c in checkpoints):
                error = '已验证的 compose checkpoint 缺失或 request_id 不匹配'
    except (OSError, ValueError, EvidenceError) as exc:
        error = f'制作状态无法读取：{exc}'
    if invalid_request or (error is not None and status not in ('cancelled', 'awaiting_agent')):
        status = 'failed'
    if status == 'historical_unverified':
        error = '历史产物未核验：缺少持久队列验证记录，未开放播放或下载；原文件与阶段记录保留。'
    history = queue.history(project_id)
    lines = [f'{e.timestamp} [{e.request_id}/{e.attempt}] {e.event}: {e.message}' for e in history]
    log_path = pdir / 'production.log'
    legacy_log = log_path.read_text(encoding='utf-8', errors='replace')[-16000:] if log_path.is_file() else ''
    return ProductionView(
        project_id=project_id, request=req, status=status,
        agent_connected=service.connected, consumer=service,
        error=error or (service.error if req and status == 'awaiting_agent' else None),
        log=(legacy_log + '\n' + '\n'.join(lines))[-16000:], history=history,
        artifact_names=artifact_names,
        media_url=f'/api/projects/{project_id}/media/final.mp4' if status == 'completed' and error is None else None,
    )
