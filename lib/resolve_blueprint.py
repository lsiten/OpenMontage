from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable
from urllib.parse import urlparse

from jsonschema import Draft202012Validator


SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schemas/artifacts/resolve_blueprint.schema.json"
SUPPORTED_OPERATIONS = frozenset(
    {
        "create_new_project",
        "create_new_timeline",
        "set_timeline_format",
        "add_video_clip",
        "add_audio_clip",
        "save_new_project",
    }
)


class BlueprintError(ValueError):
    pass


class BlueprintValidationError(BlueprintError):
    pass


class UnsupportedOperationError(BlueprintError):
    pass


class PartialExecutionError(BlueprintError):
    def __init__(self, completed_operations: tuple[str, ...], failed_operation: str, cause: Exception):
        self.completed_operations = completed_operations
        self.failed_operation = failed_operation
        self.cause = cause
        super().__init__(
            f"operation {failed_operation!r} failed after {len(completed_operations)} completed operation(s): {cause}"
        )


@dataclass(frozen=True)
class FrameRange:
    start_frame: int
    end_exclusive_frame: int

    def __post_init__(self) -> None:
        if self.start_frame < 0 or self.end_exclusive_frame <= self.start_frame:
            raise BlueprintError("frame range must be non-empty and half-open")


def load_schema() -> dict[str, Any]:
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def validate_blueprint(payload: dict[str, Any], *, check_media: bool = True) -> None:
    errors = sorted(Draft202012Validator(load_schema()).iter_errors(payload), key=lambda error: list(error.path))
    messages = [f"{'.'.join(map(str, error.path)) or '<root>'}: {error.message}" for error in errors]
    if messages:
        raise BlueprintValidationError("schema validation failed: " + "; ".join(messages))

    project = payload["project"]
    timeline = payload["timeline"]
    if project["fps_numerator"] <= 0 or project["fps_denominator"] <= 0:
        raise BlueprintValidationError("timeline fps must be a positive rational")
    if timeline["end_exclusive_frame"] <= timeline["start_frame"]:
        raise BlueprintValidationError("timeline must use a non-empty half-open frame range")
    if payload["unsupported_operations"]:
        raise UnsupportedOperationError(
            "unsupported operations explicitly requested: " + ", ".join(payload["unsupported_operations"])
        )
    if payload["audio"]["music"] and (
        not payload["audio"].get("music_rights_ref")
        or not payload["audio"].get("music_rights_sha256")
    ):
        raise BlueprintValidationError("music requires a verified rights sidecar reference and digest")

    for index, clip in enumerate(payload["clips"], start=1):
        _validate_clip_range(clip, f"clips[{index - 1}]")
    for name in ("narration", "music", "sfx"):
        for index, asset in enumerate(payload["audio"][name], start=1):
            _validate_audio_range(asset, f"audio.{name}[{index - 1}]")
    if check_media:
        validate_media_sources(payload)


def _validate_clip_range(clip: dict[str, Any], label: str) -> None:
    if clip["source_end_exclusive_frame"] <= clip["source_in_frame"]:
        raise BlueprintValidationError(f"{label} source range must be half-open and non-empty")
    if clip["record_end_exclusive_frame"] <= clip["record_in_frame"]:
        raise BlueprintValidationError(f"{label} record range must be half-open and non-empty")
    if clip["speed"] != 1:
        raise UnsupportedOperationError(f"{label} speed change is unsupported")


def _validate_audio_range(asset: dict[str, Any], label: str) -> None:
    if asset["record_end_exclusive_frame"] <= asset["record_in_frame"]:
        raise BlueprintValidationError(f"{label} record range must be half-open and non-empty")


def fps_fraction(numerator: int, denominator: int) -> tuple[int, int]:
    if numerator <= 0 or denominator <= 0:
        raise BlueprintError("fps must be a positive rational")
    common = _gcd(numerator, denominator)
    return numerator // common, denominator // common


def _gcd(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return abs(left)


def to_resolve_inclusive(frame_range: FrameRange) -> dict[str, int]:
    return {
        "start_frame": frame_range.start_frame,
        "end_frame_inclusive": frame_range.end_exclusive_frame - 1,
    }


def from_resolve_inclusive(start_frame: int, end_frame_inclusive: int) -> FrameRange:
    if start_frame < 0 or end_frame_inclusive < start_frame:
        raise BlueprintError("Resolve inclusive frame range is invalid")
    return FrameRange(start_frame, end_frame_inclusive + 1)


def canonical_blueprint_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def expected_idempotency_key(payload: dict[str, Any]) -> str:
    digest = canonical_blueprint_sha256(payload)
    approval = "|".join(payload["approval_refs"])
    identity = f"{payload['project']['new_project_name']}|{payload['timeline']['new_timeline_name']}"
    return hashlib.sha256(f"{approval}|{digest}|{identity}".encode("utf-8")).hexdigest()


def resolve_approved_source(source_path: str, approved_roots: Iterable[str]) -> Path:
    parsed = urlparse(source_path)
    if parsed.scheme or source_path.startswith("//"):
        raise BlueprintError(f"remote source is not allowed: {source_path}")
    path = Path(source_path)
    if not path.is_absolute():
        raise BlueprintError(f"source path must be absolute: {source_path}")
    if ".." in path.parts:
        raise BlueprintError(f"path traversal is not allowed: {source_path}")

    roots = [_normal_root(root) for root in approved_roots]
    if not roots:
        raise BlueprintError("at least one approved media root is required")
    for root in roots:
        if _contains_symlink(root) or not root.is_dir():
            raise BlueprintError(f"approved media root must be a real directory without symlinks: {root}")
    resolved = path.resolve(strict=False)
    for root in roots:
        try:
            resolved.relative_to(root.resolve(strict=False))
        except ValueError:
            continue
        if _contains_symlink(path):
            raise BlueprintError(f"symlink media paths are not allowed: {source_path}")
        if not path.is_file():
            raise BlueprintError(f"media source is missing or not a regular file: {source_path}")
        return path
    raise BlueprintError(f"source is outside approved media roots: {source_path}")


def _normal_root(root: str) -> Path:
    path = Path(root)
    if not path.is_absolute():
        raise BlueprintError(f"approved media root must be absolute: {root}")
    return path.absolute()


def _contains_symlink(path: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current == current.parent:
            return False
        current = current.parent


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_media_sources(payload: dict[str, Any]) -> None:
    roots = payload["inputs"]["approved_media_roots"]
    sources = [*payload["clips"]]
    for name in ("narration", "music", "sfx"):
        sources.extend(payload["audio"][name])
    for asset in sources:
        path = resolve_approved_source(asset["source_path"], roots)
        actual = sha256_file(path)
        if actual.lower() != asset["source_sha256"].lower():
            raise BlueprintError(
                f"source hash changed for {asset['asset_id']}: expected {asset['source_sha256']}, got {actual}"
            )


def execute_authorized_operations(
    operations: Iterable[str], runner: Callable[[str], None]
) -> tuple[str, ...]:
    completed: list[str] = []
    for operation in operations:
        if operation not in SUPPORTED_OPERATIONS:
            raise UnsupportedOperationError(f"unsupported operation refused: {operation}")
        try:
            runner(operation)
        except Exception as error:
            raise PartialExecutionError(tuple(completed), operation, error) from error
        completed.append(operation)
    return tuple(completed)


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an offline Resolve blueprint without connecting to Resolve.")
    parser.add_argument("blueprint", type=Path)
    parser.add_argument("--skip-media", action="store_true")
    args = parser.parse_args()
    try:
        payload = _load_json(args.blueprint)
        validate_blueprint(payload, check_media=not args.skip_media)
    except (OSError, json.JSONDecodeError, BlueprintError) as error:
        print(json.dumps({"valid": False, "error": str(error)}, ensure_ascii=False))
        return 1
    result = {
        "valid": True,
        "blueprint_sha256": canonical_blueprint_sha256(payload),
        "idempotency_key": expected_idempotency_key(payload),
        "frame_origin": payload["timeline"]["start_frame"],
        "timeline_fps": fps_fraction(payload["project"]["fps_numerator"], payload["project"]["fps_denominator"]),
        "resolve_connection": False,
    }
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
