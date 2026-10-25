## 角色与授权
OpenMontage 视频制作小队·**工程集成**（d5dd01ea）。你是**唯一可改业务实现**的角色。按**已验收**方案/契约 LSIT-285 实现 ① 独立 PM 应用 + ② 对话式驱动。制片统筹（0640b2f5）是唯一整体验收负责人。

## 前置（阶段已解锁：方案/契约通过独立复核）
- LSIT-285 方案/契约草案已由**独立质检（d9095bea，非作者）复验 PASS**，制片统筹确认**方案/契约阶段通过**（父 LSIT-284，stage 1）。
- 待实现契约 = LSIT-285 附件 `LSIT-285-agentic-video-product-design.md`（sha256 `ecdde6209420c1b4f4577225ebd2516e50e8527f684ad0d08e90b41fdb554a51`；基线 `main@f10953d0`，worktree 分支 `agent/issue-tree/lsit-284` HEAD `b4c84eae`，`git diff main..HEAD` 空；AGPLv3；2026-10-25 实测）。
- 契约要点（须逐条实现，不偏离）：
  - ① **独立 PM 应用**：新建 `pm/` 包（与 `backlot/` 平级）；FastAPI + pydantic v2 + jsonschema + **SQLite(stdlib `sqlite3`)** + vanilla JS（沿用 `backlot/ui/` 范式，新增 `pm/ui/`，**不引入 React/Next/Vue/付费前端框架**）；CRUD + 列表/详情/状态/成本视图；复用 `backlot/state.py` 派生逻辑；数据源 = 磁盘 `projects/<id>/` + 新增可写 PM 元数据层（建议 `.pm/` SQLite，与 `projects/<id>/` 经 `project_id` 关联）。
  - ② **对话式驱动**：本地 `pm/chat` 复用 13 条 agentic 管线"管线选择"逻辑（agent 驱动，**不新增执行引擎**），复用 `registry.provider_menu`；**不冒充真实 AI 服务**；Bloome = external（第三方云端多 agent），**不复用**。
  - **backlot 关系**：并存 + 渐进升级，**不原地改写只读语义**（受 `tests/contracts/test_backlot_contract.py` 守护）。

## 任务
1. 按契约实现 `pm/` 包（后端 API + 前端 + 数据/契约层）与 `pm/chat` 对话入口。
2. **零付费/本地**：默认只暴露本地/离线能力（Remotion/HyperFrames/Piper/whisper/ffmpeg；本地 diffusion·视频 gen 需 GPU、ComfyUI localhost:8188 默认）；付费 provider（Gemini/Veo/Sora2/Kling/Flux/Imagen/ElevenLabs/Suno/Azure/Google GenAI 等）显示"未接入/需授权"，**不默认调用**；敏感/真人声音/肖像/音乐**不接入**。
3. 本地 smoke test（记录命令/退出码/日志）：`python -m pytest tests/backlot/...`、`tests/contracts/...`、`render_demo.py`、`scripts/backlot_simulate_run.py`、`python -c "from tools.tool_registry import registry; registry.discover(); registry.provider_menu()"`；**新增 `pm/` 的测试与契约，且不破坏 `test_backlot_contract.py`**。
4. 不冒充真实 AI 服务；离线替身/mock 必须标注"未接入/未验收"（不代表真实 AI 服务已接入或质量已验收）。

## 约束（硬边界）
- 零付费/本地/无付费 AI/不 publish 部署；真实 AI/付费服务未接入（mock/离线替身须标注）。
- 代码改动仅在本任务授权范围内，在**绑定 worktree**（`agent/issue-tree/lsit-284`）中进行；**保留可回滚差异**；**不擅自 commit/push/PR/部署/发布/改外部权限/启动后台巡检**。
- **不引入新付费依赖/框架；不改 `requirements*.txt`/锁文件**（如需先记录缺口，由制片统筹向用户确认，不试运行）。
- 跨 worktree 读取须核实路径/哈希/基线；不假定未提交产物自动共享。
- 未知计费/授权先记录缺口，由制片统筹向用户确认，不试运行。

## 产物
- 实际代码（`pm/` 包 + `pm/chat` + 前端 + 数据/契约层 + 测试）写入绑定 worktree。
- 登记：分支/HEAD/提交/差异/命令/退出码/日志；面向用户文件经 Multica 附件交付；登记路径/内容哈希/制作基线。

## 验收条件
- ① PM 应用：CRUD + 列表/详情/状态/成本视图 本地可运行（SQLite 持久化，与 `projects/<id>/` 经 `project_id` 关联）；② 对话入口：复用 13 管线选择逻辑、不新增执行引擎、不冒充真实 AI 服务。
- backlot 只读契约不破坏（`tests/contracts/test_backlot_contract.py` 通过）。
- 本地 smoke test 全过（记录命令/退出码/日志）；零付费/本地/无付费 AI。
- 由**独立质检（d9095bea，非作者）独立复核**，再交制片统筹（0640b2f5）整体验收；**不以作者自检当通过，不以运行结束替代验收**。

## 下一接收人
工程集成（实现/制作）→ 独立质检（d9095bea，非作者复核）→ 制片统筹（0640b2f5，整体验收）。父任务 LSIT-284 在整体验收前保持未完成，不擅自关闭。
