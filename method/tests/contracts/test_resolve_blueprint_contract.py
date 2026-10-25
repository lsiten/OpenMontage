from __future__ import annotations

import copy
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from lib.resolve_blueprint import (
    BlueprintError,
    BlueprintValidationError,
    FrameRange,
    PartialExecutionError,
    UnsupportedOperationError,
    execute_authorized_operations,
    expected_idempotency_key,
    fps_fraction,
    from_resolve_inclusive,
    resolve_approved_source,
    to_resolve_inclusive,
    validate_blueprint,
)


FIXTURE_DIR = Path(__file__).parents[1] / "fixtures/resolve_blueprint"


def load_fixture(directory: Path = FIXTURE_DIR) -> dict:
    """Bind the portable test template to its own directory, never the cwd."""
    payload = json.loads((directory / "valid.json").read_text(encoding="utf-8"))
    payload["inputs"]["approved_media_roots"] = [
        str(directory / root) for root in payload["inputs"]["approved_media_roots"]
    ]
    for clip in payload["clips"]:
        clip["source_path"] = str(directory / clip["source_path"])
    return payload


def valid_blueprint(tmp_path: Path) -> dict:
    media_root = tmp_path / "media"
    media_root.mkdir()
    media = media_root / "clip.bin"
    media.write_bytes(b"openmontage-offline-smoke\n")
    digest = hashlib.sha256(media.read_bytes()).hexdigest()
    payload = json.loads((FIXTURE_DIR / "valid.json").read_text(encoding="utf-8"))
    payload["inputs"]["approved_media_roots"] = [str(media_root)]
    payload["clips"][0]["source_path"] = str(media)
    payload["clips"][0]["source_sha256"] = digest
    return payload


def test_valid_fixture_passes_and_keeps_source_and_timeline_fps_independent(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    validate_blueprint(payload)
    assert fps_fraction(payload["project"]["fps_numerator"], payload["project"]["fps_denominator"]) == (30000, 1001)
    assert (payload["clips"][0]["source_fps"]["numerator"], payload["clips"][0]["source_fps"]["denominator"]) == (24, 1)


def test_checked_in_fixture_is_self_contained(tmp_path: Path, monkeypatch):
    relocated = tmp_path / "relocated-fixture"
    shutil.copytree(FIXTURE_DIR, relocated)
    monkeypatch.chdir(tmp_path)
    for directory in (FIXTURE_DIR, relocated):
        validate_blueprint(load_fixture(directory))


def test_schema_is_closed_and_rejects_unknown_fields(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    payload["tracks"]["unexpected"] = []
    with pytest.raises(BlueprintValidationError, match="unexpected"):
        validate_blueprint(payload, check_media=False)


def test_unused_input_source_hash_is_rejected(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    payload["inputs"]["source_sha256"] = "0" * 64
    with pytest.raises(BlueprintValidationError, match="source_sha256"):
        validate_blueprint(payload, check_media=False)


def test_unsupported_operations_are_explicitly_rejected(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    payload["unsupported_operations"] = ["captions"]
    with pytest.raises(UnsupportedOperationError, match="captions"):
        validate_blueprint(payload, check_media=False)


def test_music_requires_a_rights_sidecar_digest(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    payload["audio"]["music"] = [
        {
            "asset_id": "music-001",
            "source_path": payload["clips"][0]["source_path"],
            "source_sha256": payload["clips"][0]["source_sha256"],
            "record_in_frame": 100,
            "record_end_exclusive_frame": 160,
            "track_role": "audio"
        }
    ]
    with pytest.raises(BlueprintValidationError, match="music_rights"):
        validate_blueprint(payload)


def test_path_traversal_and_remote_sources_are_rejected(tmp_path: Path):
    root = tmp_path / "media"
    root.mkdir()
    with pytest.raises(BlueprintError, match="traversal"):
        resolve_approved_source(str(root / ".." / "secret.bin"), [str(root)])
    with pytest.raises(BlueprintError, match="remote"):
        resolve_approved_source("https://example.invalid/clip.mp4", [str(root)])


def test_approved_root_ancestors_must_not_contain_symlinks(tmp_path: Path):
    real_parent = tmp_path / "real-parent"
    real_parent.mkdir()
    linked_parent = tmp_path / "linked-parent"
    linked_parent.symlink_to(real_parent, target_is_directory=True)
    root = linked_parent / "media"
    root.mkdir()
    media = root / "clip.bin"
    media.write_bytes(b"outside the approved path\n")

    with pytest.raises(BlueprintError, match="approved media root"):
        resolve_approved_source(str(media), [str(root)])


def test_symlink_escape_is_rejected(tmp_path: Path):
    root = tmp_path / "media"
    outside = tmp_path / "outside.bin"
    root.mkdir()
    outside.write_bytes(b"outside")
    link = root / "link.bin"
    link.symlink_to(outside)
    with pytest.raises(BlueprintError, match="symlink"):
        resolve_approved_source(str(link), [str(root)])


def test_full_file_hash_change_is_rejected(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    media = Path(payload["clips"][0]["source_path"])
    media.write_bytes(b"changed\n")
    with pytest.raises(BlueprintError, match="hash changed"):
        validate_blueprint(payload)


def test_source_hash_must_match_the_bound_media_object(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    payload["clips"][0]["source_sha256"] = "0" * 64
    with pytest.raises(BlueprintError, match="hash changed"):
        validate_blueprint(payload)


def test_half_open_ranges_convert_at_resolve_boundary_only():
    internal = FrameRange(100, 160)
    assert to_resolve_inclusive(internal) == {"start_frame": 100, "end_frame_inclusive": 159}
    assert from_resolve_inclusive(100, 159) == internal
    with pytest.raises(BlueprintError, match="invalid"):
        from_resolve_inclusive(100, 99)


def test_frame_origin_is_explicit_and_preserved(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    assert payload["timeline"]["start_frame"] == 100
    assert payload["timeline"]["frame_origin"] == "explicit_start_frame"
    validate_blueprint(payload)


def test_idempotency_key_changes_with_approval_or_identity(tmp_path: Path):
    payload = valid_blueprint(tmp_path)
    first = expected_idempotency_key(payload)
    changed_approval = copy.deepcopy(payload)
    changed_approval["approval_refs"] = ["different-approval"]
    changed_identity = copy.deepcopy(payload)
    changed_identity["project"]["new_project_name"] = "another-project"
    assert first != expected_idempotency_key(changed_approval)
    assert first != expected_idempotency_key(changed_identity)


def test_partial_failure_stops_without_running_later_operations():
    calls: list[str] = []

    def runner(operation: str) -> None:
        calls.append(operation)
        if operation == "add_video_clip":
            raise RuntimeError("mock append failed")

    with pytest.raises(PartialExecutionError) as raised:
        execute_authorized_operations(
            ["create_new_project", "add_video_clip", "save_new_project"],
            runner,
        )
    assert calls == ["create_new_project", "add_video_clip"]
    assert raised.value.completed_operations == ("create_new_project",)
    assert raised.value.failed_operation == "add_video_clip"


def test_unknown_operation_is_refused_before_runner():
    with pytest.raises(UnsupportedOperationError, match="unsupported operation"):
        execute_authorized_operations(["captions"], lambda _: pytest.fail("runner must not run"))
