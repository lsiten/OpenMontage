"""Composition discovery follows the checkout layout without installing Node packages."""

from pathlib import Path

import pytest

from lib import paths
from tools.video.remotion_caption_burn import RemotionCaptionBurn
from tools.video.video_compose import VideoCompose


@pytest.mark.parametrize("layout", ["monorepo", "standalone", "standalone-named-method"])
def test_render_and_caption_use_the_same_checkout_composer(tmp_path, monkeypatch, layout):
    if layout == "monorepo":
        method = tmp_path / "method"
        composer = tmp_path / "remotion-composer"
    else:
        method = tmp_path / ("method" if layout == "standalone-named-method" else "legacy")
        composer = method / "remotion-composer"
    method.mkdir(parents=True)
    composer.mkdir(parents=True)
    (composer / "package.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(paths, "REPO_ROOT", method)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("shutil.which", lambda name: f"/local/{name}")

    tool = VideoCompose()
    assert not tool._remotion_available(), "a checkout alone must not advertise installed Remotion"
    assert RemotionCaptionBurn()._find_remotion_root() is None
    (composer / "node_modules").mkdir()
    assert tool._remotion_available()
    assert RemotionCaptionBurn()._find_remotion_root() == composer

    calls = []

    def capture_render(command, **kwargs):
        calls.append((command, kwargs["cwd"]))

    monkeypatch.setattr(tool, "run_command", capture_render)
    tool._remotion_render({
        "composition_data": {"cuts": []},
        "output_path": str(tmp_path / "out.mp4"),
    })
    assert len(calls) == 1
    assert "Explainer" in calls[0][0]
    assert Path(calls[0][1]) == composer


def test_monorepo_prefers_the_shared_composer_over_a_stale_nested_copy(tmp_path):
    method = tmp_path / "method"
    for composer in (tmp_path / "remotion-composer", method / "remotion-composer"):
        composer.mkdir(parents=True)
        (composer / "package.json").write_text("{}", encoding="utf-8")
    assert paths.remotion_composer_dir(method) == tmp_path / "remotion-composer"


def test_checked_in_demo_entry_finds_shared_props_without_rendering():
    import render_demo

    expected = paths.remotion_composer_dir()
    assert (expected / "src/index.tsx").is_file()
    assert render_demo.COMPOSER_DIR == expected
    assert "world-in-numbers" in render_demo.discover_demos()
