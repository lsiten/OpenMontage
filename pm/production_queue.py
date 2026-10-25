"""Durable request ledger. OS locks fence live local workers across restarts."""

from __future__ import annotations

import fcntl
import sqlite3
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from pm.production_types import ProductionRequest, QueueEvent, QueueRecord, RequestControl, RunStatus


class RequestConflict(RuntimeError):
    """The project/request identity or current lifecycle does not match."""


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class ProductionQueue:
    """One immutable request per project, append-only attempt events, no shared connection."""

    def __init__(self, projects_dir: Path) -> None:
        self.root = projects_dir.resolve()
        self.directory = self.root / '.pm-production'
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'queue.sqlite3'
        with self.connect() as conn:
            conn.executescript('''
                CREATE TABLE IF NOT EXISTS requests (
                    project_id TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL,
                    record TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY, project_id TEXT NOT NULL, payload TEXT NOT NULL);
            ''')

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        with closing(sqlite3.connect(self.path, timeout=10)) as conn:
            with conn:
                yield conn

    def project_dir(self, project_id: str) -> Path:
        path = self.root / project_id
        if not project_id or path.name != project_id or path.resolve().parent != self.root:
            raise RequestConflict('非法项目位置')
        return path

    @contextmanager
    def lease(self, project_id: str) -> Iterator[int | None]:
        """Hold across child execution; inherited FD also fences an orphan after parent crash."""
        self.project_dir(project_id)
        with (self.directory / f'{project_id}.lock').open('a+b') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                yield None
            else:
                # close(), rather than LOCK_UN, keeps a surviving child fenced.
                yield lock.fileno()

    def register(self, request: ProductionRequest, explicit_id: str | None = None) -> ProductionRequest:
        """Serialize API submissions and import the existing immutable handoff if present."""
        pdir = self.project_dir(request.project_id)
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT record FROM requests WHERE project_id=?', (request.project_id,)).fetchone()
            if row:
                existing = QueueRecord.model_validate_json(row[0]).request
                if existing.mode != request.mode or existing.pipeline_type != request.pipeline_type or (
                    explicit_id and existing.request_id != explicit_id
                ):
                    raise RequestConflict('项目已有不同 request_id 或制作模式；请复用原请求')
                return existing
            path = pdir / 'production_request.json'
            if path.is_file():
                existing = ProductionRequest.model_validate_json(path.read_text(encoding='utf-8'))
                if existing.project_id != request.project_id or existing.mode != request.mode or (
                    explicit_id and existing.request_id != explicit_id
                ):
                    raise RequestConflict('已有请求的项目、模式或 request_id 不匹配')
                request = existing
            record = QueueRecord(request=request)
            try:
                conn.execute('INSERT INTO requests VALUES (?, ?, ?)',
                             (request.project_id, request.request_id, record.model_dump_json()))
            except sqlite3.IntegrityError as exc:
                raise RequestConflict('request_id 已被其他项目使用') from exc
            self._event(conn, record.event('requested', '制作请求入队'))
            tmp = path.with_name(f'.production-{uuid.uuid4().hex}.tmp')
            tmp.write_text(request.model_dump_json(indent=2), encoding='utf-8')
            tmp.replace(path)
            return request

    def get(self, project_id: str) -> QueueRecord | None:
        with self.connect() as conn:
            row = conn.execute('SELECT record FROM requests WHERE project_id=?', (project_id,)).fetchone()
            return QueueRecord.model_validate_json(row[0]) if row else None

    def candidates(self) -> list[QueueRecord]:
        with self.connect() as conn:
            records = [QueueRecord.model_validate_json(r[0]) for r in conn.execute('SELECT record FROM requests ORDER BY rowid')]
            return [r for r in records if r.status in ('awaiting_agent', 'in_progress')]

    def claim(self, project_id: str) -> QueueRecord | None:
        """Caller must hold the project lease until finish; token fences delayed writers."""
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT record FROM requests WHERE project_id=?', (project_id,)).fetchone()
            if not row:
                return None
            old = QueueRecord.model_validate_json(row[0])
            if old.status not in ('awaiting_agent', 'in_progress'):
                return None
            if old.attempt:
                self._event(conn, old.event('recovering', '保留此前尝试；由 agent 从 canonical checkpoint 恢复'))
            record = old.model_copy(update={'status': 'in_progress', 'attempt': old.attempt + 1,
                                           'token': uuid.uuid4().hex, 'error': None})
            self._save(conn, record)
            self._event(conn, record.event('claimed', '消费端取得项目租约'))
            return record

    def finish(self, record: QueueRecord) -> None:
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT record FROM requests WHERE project_id=?', (record.request.project_id,)).fetchone()
            current = QueueRecord.model_validate_json(row[0])
            if current.token != record.token:
                raise RequestConflict('过期消费租约')
            if current.cancel_requested:
                record = record.model_copy(update={'status': 'cancelled', 'media_sha256': None})
            self._save(conn, record)
            self._event(conn, record.event(record.status, record.error or '消费端已释放租约'))

    def control(self, project_id: str, action: tuple[RequestControl, bool]) -> QueueRecord:
        """Cancel or explicitly resume/retry the same request; never erase failure history."""
        control, retry = action
        with self.connect() as conn:
            conn.execute('BEGIN IMMEDIATE')
            row = conn.execute('SELECT record FROM requests WHERE project_id=?', (project_id,)).fetchone()
            if not row:
                raise RequestConflict('制作请求不存在')
            record = QueueRecord.model_validate_json(row[0])
            if record.request.request_id != control.request_id:
                raise RequestConflict('request_id 不匹配')
            if retry:
                if record.status not in ('failed', 'cancelled', 'awaiting_human', 'completed'):
                    raise RequestConflict('当前状态不可重试或恢复')
                record = record.model_copy(update={'status': 'awaiting_agent', 'cancel_requested': False,
                                                   'error': None, 'media_sha256': None})
            else:
                if record.status == 'completed':
                    raise RequestConflict('已完成请求不可取消')
                status: RunStatus = 'in_progress' if record.status == 'in_progress' else 'cancelled'
                record = record.model_copy(update={'status': status, 'cancel_requested': True, 'media_sha256': None})
            self._save(conn, record)
            self._event(conn, record.event('retry_requested' if retry else 'cancel_requested', '请求恢复' if retry else '请求取消'))
            return record

    def log(self, record: QueueRecord, message: str) -> None:
        with self.connect() as conn:
            self._event(conn, record.event('agent_log', message[:4000]))

    def history(self, project_id: str) -> list[QueueEvent]:
        with self.connect() as conn:
            rows = conn.execute('SELECT payload FROM events WHERE project_id=? ORDER BY id DESC LIMIT 100', (project_id,)).fetchall()
            return [QueueEvent.model_validate_json(r[0]) for r in reversed(rows)]

    def _save(self, conn: sqlite3.Connection, record: QueueRecord) -> None:
        conn.execute('UPDATE requests SET record=? WHERE project_id=?',
                     (record.model_dump_json(), record.request.project_id))

    def _event(self, conn: sqlite3.Connection, entry: QueueEvent) -> None:
        conn.execute('INSERT INTO events(project_id, payload) VALUES (?, ?)',
                     (entry.project_id, entry.model_dump_json()))
