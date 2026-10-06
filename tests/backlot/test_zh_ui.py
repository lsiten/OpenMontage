import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is required for UI helpers")


def run_ui(code):
    result = subprocess.run(
        [NODE, "--experimental-default-type=module", "--input-type=module", "-e", code],
        cwd=ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(result.stdout)


def test_known_pipeline_and_stage_labels_are_translated():
    labels = run_ui(
        'import {LABELS} from "./backlot/ui/zh.js"; console.log(JSON.stringify(LABELS));'
    )
    for manifest_path in (ROOT / "pipeline_defs").glob("*.yaml"):
        manifest = yaml.safe_load(manifest_path.read_text())
        assert manifest_path.stem in labels
        for stage in manifest["stages"]:
            assert stage["name"] in labels
            for artifact in stage.get("produces", []):
                assert artifact in labels


def test_status_mapping_preserves_unknown_technical_identifiers():
    values = run_ui('''
        import {label, pipelineLabel} from "./backlot/ui/zh.js";
        console.log(JSON.stringify([
            label("pending"), label("completed"), label("awaiting_human"),
            label("custom_stage"), label("toString"), pipelineLabel("unknown"),
            pipelineLabel("cinematic"), label("用户原文 English /path.json")
        ]));
    ''')
    assert values == [
        "尚未执行", "已完成", "待人工审核", "custom_stage", "toString",
        "未识别的制作流程", "电影短片", "用户原文 English /path.json",
    ]


def test_decision_and_shot_enums_have_chinese_labels():
    labels = run_ui(
        'import {LABELS} from "./backlot/ui/zh.js"; console.log(JSON.stringify(LABELS));'
    )
    decisions = json.loads((ROOT / "schemas/artifacts/decision_log.schema.json").read_text())
    categories = decisions["properties"]["decisions"]["items"]["properties"]["category"]["enum"]
    assert all(category in labels for category in categories)
    scene_schema = json.loads((ROOT / "schemas/artifacts/scene_plan.schema.json").read_text())
    shots = scene_schema["properties"]["scenes"]["items"]["properties"]["shot_language"]["properties"]
    for field in ("shot_size", "camera_movement", "lighting_key"):
        assert all(value in labels for value in shots[field]["enum"])
    values = run_ui('''
        import {shotLabel, label} from "./backlot/ui/zh.js";
        console.log(JSON.stringify([shotLabel("medium"), label("medium")]));
    ''')
    assert values == ["中景", "中"]


def test_error_copy_distinguishes_missing_project_server_and_network():
    values = run_ui('''
        import {loadError} from "./backlot/ui/zh.js";
        console.log(JSON.stringify([
            loadError({status:404}, true), loadError({status:503}, true),
            loadError({status:403}), loadError(new TypeError("Failed to fetch"))
        ]));
    ''')
    assert values == [
        "项目不存在或已移除", "本地服务暂时不可用，请稍后重试",
        "无权读取此内容", "加载失败，请检查本地服务连接后重试",
    ]


def test_time_helpers_use_chinese_and_preserve_timecodes():
    values = run_ui('''
        import {fmtAgo, fmtClock, fmtDuration, fmtMoney} from "./backlot/ui/lib.js";
        Date.now = () => 200000000;
        console.log(JSON.stringify([
            fmtAgo(199999), fmtAgo(199400), fmtAgo(192800), fmtAgo(27200),
            fmtClock("not-a-date"), fmtDuration(65), fmtMoney(1.25)
        ]));
    ''')
    assert values == ["刚刚", "10分钟前", "2小时前", "2天前", "", "1:05", "$1.25"]


def test_fetch_error_retains_original_http_status():
    values = run_ui('''
        import {getJSON} from "./backlot/ui/lib.js";
        globalThis.fetch = async () => ({ok: false, status: 503});
        try { await getJSON("/api/projects"); }
        catch (error) { console.log(JSON.stringify([error.status, error.message])); }
    ''')
    assert values == [503, "503 /api/projects"]


def test_html_declares_chinese_and_has_initial_loading_state():
    for filename in ("index.html", "board.html"):
        content = (ROOT / "backlot" / "ui" / filename).read_text()
        assert '<html lang="zh-CN">' in content
        assert "正在加载" in content


def test_no_checkpoints_does_not_show_default_stage_rail():
    content = (ROOT / "backlot" / "ui" / "board.js").read_text()
    assert "if (s.has_pipeline_state) app.append(renderRail(s));" in content
    assert "暂无制作流程状态。" in content
    assert "不代表实时制作进度或成片验收" in content
