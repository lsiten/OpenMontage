# Backlot — the living storyboard

A read-only local board that shows a production happening: pipeline stages
lighting up, the script as a screenplay page, the scene plan as a filmstrip
that fills in as assets generate, decisions, spend, and activity — all
derived from what the pipeline already writes to `projects/<id>/`.

```bash
python -m backlot open <project-id>   # start server if needed + open browser
python -m backlot open                # library view (all projects)
python -m backlot serve --port 4750   # run the server in the foreground
```

## How it stays live

No agent involvement. A `watchfiles` watcher on `projects/` publishes change
notifications over SSE; the browser refetches board state. State sources:

| Board element | Disk source |
|---|---|
| identity / rail order | `project.json` + `pipeline_defs/<type>.yaml` |
| stage states, gates, versions | `checkpoint_<stage>.json` + `history/` |
| script card / modal | `artifacts/script.json` |
| filmstrip cards | `scene_plan × script × asset_manifest` join |
| generating shimmer, activity | `events.jsonl` (written by `BaseTool` instrumentation) |
| cost meter | checkpoint `cost_snapshot` |
| renders | `renders/*.mp4` (+ root-level mp4 heuristic) |

Projects without checkpoints degrade gracefully to a "what the watcher
found" view — media, snapshots, renders.

**Replay**: a completed run can be scrubbed end-to-end (▶ REPLAY RUN on the
board) — reconstructed from checkpoint history and event timestamps.

Try it without a real production:

```bash
python scripts/backlot_simulate_run.py          # live demo run (~1 min)
python -m backlot open backlot-demo-run
```

Design doc: `internal/design/LIVING_STORYBOARD.md`.

## 简体中文界面

Backlot 默认使用简体中文。项目库、制作看板、审核摘要、脚本与旁白弹窗、
历史回放及加载/错误提示均在展示层中文化；内部状态、API 键、文件路径、
技术标识、原始 JSON、日志及用户自定义内容保持原样。已知术语集中在
`ui/zh.js`，新增阶段或产物时同步补充映射；未知技术标识如实保留。
原应用没有语言切换功能，本次没有引入国际化依赖或新增语言切换产品。

无制作检查点的项目显示“暂无制作流程状态”，不显示默认待执行阶段轨道，
只展示已有媒体记录，不代表实时制作进度、独立审核通过或视频制作完成。
界面使用本机中文字体回退，不依赖在线字体下载。

本地回归（使用已有项目隔离环境，不调用生成服务）：

```bash
python -m pytest tests/backlot/test_zh_ui.py tests/backlot/test_state.py tests/backlot/test_server.py tests/backlot/test_gate_scenarios.py tests/contracts/test_backlot_contract.py -q
python -m pytest tests/backlot/test_ui_bug_bash.py -q
```

第二组需要既有 Playwright 和 Chromium；未安装时不代表浏览器验收通过。
