# 独立质检复验结论 — LSIT-288 实现/制作产物（①独立PM应用 + ②对话式驱动）

**审查角色**：OpenMontage-独立质检（d9095bea，非作者）
**审查对象**：LSIT-288 工程集成（d5dd01ea）交付；父任务 LSIT-284（stage 3 in_review）
**审查基线**：main@f10953d0（f10953d09bbdb2a400af6ba4b856b7d49d7846d8），AGPLv3，2026-10-25 实测
**方法**：不采信作者自检；一律实测（命令/退出码/证据）。在隔离 clean base（`git worktree add main@f10953d0`，无预存 pm/）解压交付 tgz 后复跑，避免工作区污染。

## 结论：**通过（PASS）**，含 1 项 minor 偏差（不阻断）

①② 本地可运行且符合契约、约束全遵守、smoke 全过、backlot 只读契约未破坏 → 报制片统筹（0640b2f5）整体验收。
1 项 minor：契约/任务列 `jsonschema` 但实现未用（pydantic v2 提供等价校验，非功能性）。

---

## 逐项验证结果

### 1. 产物真实完整 — **PASS**
- 两附件可下载：manifest 4810B、tgz 26918B（与任务声明一致）。
- tgz `sha256 = ef9fee3c645deaee3668b2b77444260bc778f95509503f0295c54231ee46ac39`，与任务/manifest 声明**逐位一致**。
- 解压 19 文件（pm/ 14 + tests/pm/ 5）；**逐文件 sha256 与 manifest 全部一致**（19/19）。
- tgz 仅含 pm/ + tests/pm/，**无基线文件改动**（纯增量）。

### 2. ① 独立 PM 应用（契约 LSIT-285）— **PASS**（minor 见下）
- 新建 `pm/`（与 backlot 平级）✓；FastAPI✓ pydantic v2（2.13.5, `BaseModel/Field/field_validator`）✓ sqlite3(stdlib)✓ vanilla JS（`pm/ui/` 无 React/Next/Vue）✓。
- **minor 偏差**：契约/任务列 `pydantic v2 + jsonschema`，实现仅用 pydantic v2、**未用 jsonschema**；但 pydantic v2 提供等价 schema 校验（`pm/schemas.py` 全模型化），功能意图已达成 → 记为 minor、不阻断。
- CRUD + 列表/详情/状态/成本视图本地可运行：HTTP 全通过（list/get/status/cost/detail 6/6）。
- SQLite 持久化：跨连接 reset 后仍可加载同一 project（验证通过）。
- 经 `project_id` 与磁盘 `projects/<id>/` 关联：trigger 写 `projects/<id>/project.json` marker（验证存在）。
- 只写 PM 层、不回写 backlot 只读派生文件：`pm/` 仅 `import`/读 `backlot.state`（read-only），backlot 只读契约测试未破坏（见 5）。

### 3. ② 对话式驱动（契约 LSIT-285）— **PASS**
- `list_pipelines()` = **13**（animated-explainer/animation/avatar-spokesperson/character-animation/cinematic/clip-factory/documentary-montage/framework-smoke/hybrid/localization-dub/podcast-repurpose/screen-demo/talking-head）。
- `pm/pipeline_select.py` = 本地确定性关键词/特征打分，显式标注 "NOT a paid LLM call and NOT a real AI service"；**不新增执行引擎**。
- `pm/capabilities.py` 复用 `tools.tool_registry.registry.provider_menu()`（report-only）。
- 输入自然语言 → 输出 `{pipeline_type, concept, cost_estimate(local/paid), approval_items}`：实测 pipeline_type=screen-demo、`concept.is_ai_generated=False`、`total_estimated_usd=0.0`、approval_items 列表（6 项）。
- `/api/chat/trigger` 创建项目：`notes="由对话入口创建；未调用付费 provider。"`（含"未调用付费 provider"）、status=draft、requires_approval=True。
- **不直接调用付费 provider**：`pm/` 全量 grep 无 openai/google/elevenlabs/… 等付费 provider import、无 api_key/env 密钥；唯一网络用法是 `__main__.py` 本地 `127.0.0.1` health 探测。
- **Bloome 未复用**：`pm/` 无任何 Bloome 引用。

### 4. 约束遵守（实测）— **PASS**
- 零付费/本地/无付费 AI/不 publish 部署：付费能力（Gemini/Veo/Sora2/Kling/Flux/Imagen/ElevenLabs/Suno/Azure/Google GenAI 等）仅"报告"，`/api/capabilities` 中 paid 55 项全部标 `未接入/需授权`，**不默认调用**。
- 未改无关/已跟踪文件：交付 tgz 仅 `pm/`+`tests/pm/`；基线 main@f10953d0 完整；clean base 应用后 `git diff main..HEAD` 等价为空（交付为纯增量）。
- 未 commit/push/PR/部署/发布：作者声明交付态 lsit-287@f1c31504 为 no-op 基线 marker（`git diff main..f1c31504` 空、pm/ 未跟踪）；交付经 tgz，非 commit。
- 不冒充真实 AI 服务：`concept.is_ai_generated=False`、`generated_by="local-heuristic (not an AI service)"`；paid 行标 `未接入/需授权`；`__init__.py` 声明离线/未接入标 "未接入/未验收"。

### 5. 独立复跑 smoke（自行复跑，不采信作者输出）— **PASS**
- `pytest tests/pm` → **22 passed**，exit 0。
- `pytest tests/backlot tests/contracts/test_backlot_contract.py tests/contracts/test_pipeline_catalog.py` → **100 passed, 1 skipped**，exit 0（backlot 只读契约未破坏）。
- `python -c "from tools.tool_registry import registry; registry.discover(); registry.provider_menu()"` → 24 类能力 dict，report-only，exit 0。
- `python render_demo.py --list` → 3 个 zero-key demo（code-to-screen/focusflow-pitch/world-in-numbers），exit 0。
- `smoke_pm.py` **不在交付 tgz 内**（作者已排除）→ 无法复跑作者原脚本；故独立编写等价 smoke（`smoke_qa.py`，隔离 DB/projects）复验作者声明的 5 项 → **24/24 通过**：health、chat plan（输出形状+is_ai_generated=False+total=0.0）、chat trigger（notes 含"未调用付费 provider"+status/req）、capabilities（117/62/55+note）、CRUD 持久化（跨 reset）、detail、RLock 24 并发无死锁。

### 6. 复核 4 处修复正确且无回归 — **PASS**
- `store.py` `_lock=threading.RLock()`（重入锁，消除 create_project→_make_project_id 同线程自死锁）✓；24 并发 create 实测无挂起。
- `update_project`：`fields.pop("updated_by")` + `args=list(fields.values())+[_now(), project_id]` 与 `SET {fields}, updated_at=? WHERE project_id=?` 占位符对齐 ✓；实测 set approved=True 生效。
- `db.py` `connect(..., check_same_thread=False)`（跨线程池安全，RLock 串行）✓。
- `server.py` `/api/capabilities` `local_available` 用 `c.get("status")`（model_dump 后 dict）✓。

### 7. 诚实记录核对 — **PASS（确为基线/环境）**
- `scripts/backlot_simulate_run.py --fast` 复跑 → **exit 1**，`CheckpointValidationError: ... stage 'script' cannot advance; incomplete or missing: ['proposal']`（基线脚本 scripts/backlot_simulate_run.py 第 100 行跳过 proposal 前置 + 基线 lib/checkpoint.py 强制阶段序）。交付 tgz 未含这两个基线文件 → **确为基线既有缺陷，非 pm/ 引入**。建议队长另行派发修复（属工程基线，非本 pm/ 交付）。
- `render_demo.py` 完整渲染未跑（需 Node+Remotion 真实渲染；Remotion 运行时，非 pm/ 交付）；已跑 `--list`（3 demo，OK）→ 与作者记录一致。

### 8. 分支/基线差异核实 — **PASS（差异不影响验收，附说明）**
- 基线 main@f10953d0 正确（`git rev-parse main` = f10953d09bbdb2a400af6ba4b856b7d49d7846d8）。
- 作者声明交付态 lsit-287@f1c31504：`f1c31504` = "chore(agent): baseline — the task worktree started here"，位于 f10953d0 之上 → `git diff main..f1c31504` 空、pm/ 未跟踪 → 与 manifest 声明一致。
- 任务期望 lsit-284（b4c84eae）vs 交付 lsit-287（f1c31504）：因 LSIT-287 已 cancelled/duplicate_of LSIT-288 的路由差异；**交付经 tgz，与该分支绑定无关，不影响验收**。
- 说明（minor，不影响验收）：当前 lsit-287 分支 tip 已变为 `cbb4e3ea`（"chore(agent): uncommitted changes from task"，其后置提交了 pm/），晚于作者交付态；tgz 交付物本身不受影响（哈希已核）。

---

## 未覆盖项
- `smoke_pm.py` 原脚本不在交付 tgz 内 → 无法复跑作者原 smoke；已用等价 `smoke_qa.py` 独立复验其声明项（结论一致）。
- `render_demo.py` 完整渲染未跑（需 Node+Remotion；Remotion 运行时，非 pm/ 交付范围）；仅复跑 `--list`。
- 本审查在隔离 clean base（f10953d0）+ 交付 tgz 复跑，未采信工作区预存 untracked pm/（避免污染）。
- 本次为"零付费/本地技术测试链"验收，**不代表真实 AI 服务已接入或生成质量已验收**（离线/未接入能力仅为"报告"，已标注）。

## 问题清单
- **minor（不阻断）**：契约 LSIT-285 及任务声明后端 `pydantic v2 + jsonschema`，实现仅用 pydantic v2、未用 jsonschema。pydantic v2 提供等价 schema 校验，功能意图达成；建议制片统筹/工程集成确认是否接受 pydantic 替代 jsonschema，或要求补 jsonschema 校验。

## 证据基线
- 环境：`.venv` Python 3.10.18 / fastapi 0.142.2 / pydantic 2.13.5 / jsonschema / pytest 9.1.1。
- 复跑均在 clean base（main@f10953d0）+ 交付 tgz（sha256 ef9fee3c…46ac39）；隔离 `OPENMONTAGE_PM_DB`/`OPENMONTAGE_PROJECTS_DIR`。
- 契约依据 LSIT-285 附件 sha256 ecdde620…554a51（13629B）已核一致。

## 下一接收人
**独立质检（d9095bea）→ 制片统筹（0640b2f5，整体验收）**。父任务 LSIT-284 在整体验收前保持未完成（in_progress），本任务不擅自关闭父任务。

---
**交接**：本次独立复验完成，结论 **通过**（含 1 项 minor 偏差，不阻断）。请制片统筹整体验收。[@制片统筹](mention://agent/0640b2f5-0997-424c-8075-b97508a13e36)
