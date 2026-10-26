"""Read-only delivery checks. These never choose or advance a production stage."""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from lib.checkpoint import validate_checkpoint
from lib.pipeline_loader import load_pipeline_readonly
from pm.production_types import ProductionRequest, Record
from schemas.artifacts import validate_artifact


class EvidenceError(RuntimeError):
    """Canonical delivery evidence is missing, inconsistent, or invalid."""


class CheckpointMetadata(BaseModel):
    model_config = ConfigDict(frozen=True)
    request_id: str = ''


class CheckpointIdentity(BaseModel):
    model_config = ConfigDict(frozen=True)
    project_id: str
    pipeline_type: str
    stage: str
    status: Literal['completed', 'failed', 'in_progress', 'awaiting_human']
    human_approved: bool = False
    metadata: CheckpointMetadata = Field(default_factory=CheckpointMetadata)
    error: str | None = None


def read_checkpoint(path: Path) -> CheckpointIdentity:
    if path.resolve().parent != path.parent.resolve():
        raise EvidenceError('checkpoint 位于本项目之外')
    raw = path.read_text(encoding='utf-8')
    validate_checkpoint(json.loads(raw))
    return CheckpointIdentity.model_validate_json(raw)


class DeliveryProof(Record):
    media_sha256: str
    evidence_sha256: str


def evidence_digest(pdir: Path) -> str:
    """Bind playback to the checkpoints and artifacts verified at worker completion."""
    digest = hashlib.sha256()
    paths = sorted([*pdir.glob('checkpoint_*.json'), *(pdir / 'artifacts').glob('*.json')])
    for path in paths:
        if not path.resolve().is_relative_to(pdir.resolve()):
            raise EvidenceError('产物位于本项目之外')
        digest.update(str(path.relative_to(pdir)).encode())
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def verify_delivery(request: ProductionRequest, pdir: Path) -> DeliveryProof:
    """Verify the agent's completion claim against the same project's canonical evidence."""
    manifest = load_pipeline_readonly(request.pipeline_type)
    for stage in manifest['stages']:
        name = stage['name']
        checkpoint = read_checkpoint(pdir / f'checkpoint_{name}.json')
        if (checkpoint.project_id, checkpoint.pipeline_type, checkpoint.stage) != (
            request.project_id, request.pipeline_type, name
        ) or checkpoint.metadata.request_id != request.request_id:
            raise EvidenceError('阶段证据 project_id/pipeline/request_id 不一致')
        if checkpoint.status != 'completed':
            raise EvidenceError('尚有未完成或待审批的阶段')
        if stage.get('human_approval_default') and not checkpoint.human_approved:
            raise EvidenceError('阶段缺少原管线人工审批记录')
        if name == 'compose':
            break
    else:
        raise EvidenceError('管线没有 compose 成片证据')
    video = pdir / 'renders/final.mp4'
    if not video.is_file() or video.stat().st_size == 0 or not video.resolve().is_relative_to(pdir.resolve()):
        raise EvidenceError('成片文件缺失、为空或越出本项目')
    report = json.loads((pdir / 'artifacts/render_report.json').read_text(encoding='utf-8'))
    validate_artifact('render_report', report)
    paths = [Path(o['path']) for o in report['outputs']]
    if not any((p if p.is_absolute() else pdir / p).resolve() == video.resolve() for p in paths):
        raise EvidenceError('render_report 未关联本项目成片')
    review = json.loads((pdir / 'artifacts/final_review.json').read_text(encoding='utf-8'))
    validate_artifact('final_review', review)
    reviewed = Path(review['output_path'])
    if review['status'] != 'pass' or (reviewed if reviewed.is_absolute() else pdir / reviewed).resolve() != video.resolve():
        raise EvidenceError('final_review 未通过或关联到其他成片')
    probe = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(video)],
                           capture_output=True, timeout=20, check=True)
    data = json.loads(probe.stdout)
    streams = [s for s in data['streams'] if s.get('codec_type') == 'video']
    if len(streams) != 1:
        raise EvidenceError('成片没有唯一视频轨')
    if request.spec:
        stream, spec = streams[0], request.spec
        if (stream['width'], stream['height'], stream['avg_frame_rate'], int(stream.get('nb_frames', 0))) != (
            spec.width, spec.height, f'{spec.fps}/1', spec.duration_seconds * spec.fps
        ) or abs(float(data['format']['duration']) - spec.duration_seconds) > 0.05:
            raise EvidenceError('成片不符合已批准技术规格')
        plan = json.loads((pdir / 'artifacts/scene_plan.json').read_text(encoding='utf-8'))
        if len(plan['scenes']) != spec.shots:
            raise EvidenceError('分镜数量不符合已批准技术规格')
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(video), '-f', 'null', '-'],
                   capture_output=True, timeout=60, check=True)
    return DeliveryProof(media_sha256=hashlib.sha256(video.read_bytes()).hexdigest(), evidence_sha256=evidence_digest(pdir))
