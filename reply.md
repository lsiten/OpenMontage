## 实现/制作完成（按已验收 LSIT-285 契约）— 交独立质检复验

> 说明：本任务 LSIT-287 已被平台标记为 `cancelled`（`duplicate_of` LSIT-288）。同一目标、同属本 agent（d5dd01ea）的活跃任务为 **LSIT-288（in_progress）**，故在此交付。

### 目标达成
按契约实现两层能力，写入绑定 worktree（分支 `agent/issue-tree/lsit-287`，HEAD `f1c31504`；`git diff main..HEAD` 空 = 基线 `main@f10953d0`）：
1. **独立 PM 应用** `pm/`（与 `backlot/` 平级）：FastAPI + pydantic v2 + **SQLite(stdlib)** + vanilla JS；CRUD + 列表/详情/状态/成本视图；经 `project_id` 与磁盘 `projects/<id>/` 关联；只写 PM 层，不回写 backlot 只读派生文件。
2. **对话式驱动** `pm/chat`：复用 13 条 agentic 管线选择逻辑（agent 驱动，**不新增执行引擎**）；输入自然语言 → 输出 `{pipeline_type, concept, cost_estimate(本地/付费分类), 需审批项}` → 触发创建项目；**不直接调用付费 provider**。

### 本轮修复 4 处（仅 pm/ 未跟踪层，`git diff --stat HEAD` 空，未碰基线）
- `store.py`：`_lock` 改 `RLock`。根因是 `create_project` 持锁后调用 `_make_project_id` 再取同一**非重入**锁 → 同线程自死锁（上轮"hang"真因，非进程争用）。
- `store.py`：`update_project` SQL 占位符/参数错位（状态/预算更新匹配不到行）→ 已修正。
- `db.py`：`connect()` 加 `check_same_thread=False`（单连接被 FastAPI 线程池跨线程复用 → `ProgrammingError`）。
- `server.py`：`/api/capabilities` 的 `local_available` 用 `c.get("status")`（local 已是 dict 列表）。

### 验证证据（命令 / 退出 / 结果）
- `pytest tests/pm` → **22 passed**（exit 0）。
- 基线守护 `pytest tests/backlot tests/contracts/test_backlot_contract.py tests/contracts/test_pipeline_catalog.py` → **100 passed, 1 skipped**（与 pm 前基线一致，未破坏 backlot 只读契约）。
- 本地 smoke（隔离 temp DB，`python ./smoke_pm.py`）→ **ALL PASS**（exit 0）：`/api/health`、`/api/chat` plan（→ screen-demo + 本地/付费成本分类）、`/api/chat/trigger`（建项目，`notes="未调用付费 provider"`）、`/api/capabilities`（117 项：local 62 / paid 55，54/55 标注 `未接入/需授权`）、CRUD 状态/预算持久化、detail。
- 零付费入口 `python -c "from tools.tool_registry import registry; registry.discover(); registry.provider_menu()"` → 24 能力，report-only（exit 0）。
- `render_demo.py --list` → 列出 3 个 zero-key demo（exit 0）。

### 硬边界确认
全程零付费/本地/无付费 AI；付费 provider 仅显示 `未接入/需授权`、不默认调用；未 commit/push/PR/部署/发布；未改 `requirements*.txt`/锁文件；未触碰 backlot 只读派生文件。**未冒充真实 AI 服务**（离线/未接入能力仅为报告，不代表已接入或生成质量已验收）。

### 产物登记
`pm/` + `tests/pm/` 全部未跟踪新增；逐文件路径/内容 sha256/制作基线见附件 `artifacts-manifest.md`；可下载包 `pm-deliverable.tgz`（26918 字节，sha256 `ef9fee3c645…`）。

### 未覆盖 / 待办
- `scripts/backlot_simulate_run.py --fast` 失败（`CheckpointValidationError`：script 跳过 proposal 前置）——**基线脚本既有缺陷**（脚本与 `lib/checkpoint.py` 均为已跟踪基线文件，本轮未改），非 pm/ 引入；按角色仅记录，建议队长派发修复任务。
- `render_demo.py` 完整 Remotion 渲染未跑（需 Node+Remotion，重/慢/可能联网，非 pm/ 交付）。

### 交接
不自审、不关闭父任务。LSIT-288 → `in_review`。请 **独立质检（d9095bea，非作者）** 复验 → **制片统筹（0640b2f5）** 整体验收。父任务 LSIT-284 在整体验收前保持未完成。
