# LSIT-286 独立质检复验报告 — LSIT-285 方案/契约草案

**结论：通过（PASS）**
**审查范围**：仅本次 LSIT-285 方案/契约草案（非代码设计文档）；不代替制片统筹关闭父任务、不承诺生产服务质量。
**审查人**：OpenMontage-独立质检（d9095bea，非作者）。**下一接收人**：制片统筹（0640b2f5，整体验收）。

## 版本 / 数据时间 / 基线
- 附件：`LSIT-285-agentic-video-product-design.md`（attachment id `01a171ec-f743-71a2-bbb7-7a9cc2855407`，13629 字节）
- 内容哈希（复算一致）：sha256 `ecdde6209420c1b4f4577225ebd2516e50e8527f684ad0d08e90b41fdb554a51`
- 制作基线：`main@f10953d0`（worktree 分支 `agent/issue-tree/lsit-284`，HEAD `b4c84eae`）；AGPLv3；2026-10-25 实测
- 复算环境：`git diff main..HEAD --name-status` 为空（exit 0）

## 逐条验证（命令 / 退出码 / 证据，不采信作者自检）

### 1. 产物真实可评审 —— 通过
- 可下载：`multica attachment download 01a171ec-...` 成功，落地 13629 字节（与登记一致）。
- 哈希一致：`shasum -a 256` = `ecdde6209420c1b4f4577225ebd2516e50e8527f684ad0d08e90b41fdb554a51`，与 issue 登记完全一致（exit 0）。
- 内容完整：§0 基线核实 + §1–§4 四问 + §5 风险 + §6 验收口径 + §7 产物登记 + §8 下一接收人 全部存在（`cat` 通读 111 行 UTF-8）。

### 2. 四问均有明确、可评审结论（§1–§4）—— 通过
逐条对照 `main@f10953d0` 实测，结论成立且可拆实现：
- **① 落点/技术栈**：`pm/` 包 + FastAPI/pydantic/jsonschema/SQLite(stdlib)/vanilla JS，零付费/本地/无付费 AI。
  - 证据：`requirements.txt`（main）含 `pydantic>=2.0`、`jsonschema>=4.20`、`fastapi>=0.110`、`uvicorn>=0.29`、`watchfiles>=0.21`；`backlot/ui/` 为 vanilla `board.html/js/css`、`index.html`、`lib.js`、`library.js`、`zh.js`（无前端框架）。
- **② backlot 关系**：并存 + 渐进升级，不原地改写只读语义，受 `test_backlot_contract.py` 守护。
  - 证据：`backlot/server.py` 第 5 行 "The server never writes to project directories"；`backlot/state.py` 存在；`tests/contracts/test_backlot_contract.py` 存在。
- **③ 对话入口**：本地 `pm/chat` 复用 13 条 agentic 管线"管线选择"逻辑，不新增执行引擎，不冒充真实 AI 服务，Bloome 为 external 未复用。
  - 证据：`pipeline_defs/` 实测 13 条（animated-explainer…talking-head，与文档枚举一致）；全仓库无 `chat`/`conversation`/`/pm/` 文件 → 当前确无本地对话入口（与"新增"一致）；`README.md` 第 60–61 行 Bloome = "multiple AI agents … runs in the cloud"（external，非本地/付费）。
- **④ 零付费/本地边界**：本地可行 vs 付费=未接入缺口不试运行，成本/授权边界清晰。
  - 证据：`tools/cost_tracker.py` 含 `estimate`/`reserve`/`reserve`/`reconcile`/`cost_log.json`/`BudgetMode`/`single_action_approval_usd`/`require_approval_for_new_paid_tool`；§4 将 Gemini/Veo/Sora2/Kling/Flux/ElevenLabs 等列"未接入缺口/不试运行"，敏感/真人声音/肖像/音乐"不接入"。

### 3. 约束遵守（实测，不采信作者声明）—— 通过
- **未改业务代码/依赖锁**：`git diff main..HEAD --name-status` 为空（exit 0）；`git status` 仅未跟踪运行时上下文（`.multica/`、`dl/`、`plan-contract/`、`next-step.json`、`pA.json`、`pB.json`、`parent-handoff.md`、`probe*.json`、`qa-285-desc.md`、`reply.md`、`wakeup-instruction.md`），无业务源码/`requirements*.txt`/锁文件改动。
- **未 commit/push/PR/部署/发布**：HEAD `b4c84eae` = "chore(agent): baseline — the task worktree started here"（no-op 本地 baseline，仅在本 worktree 分支，diff 空）。
- **未调用付费/外部 AI；未冒充真实 AI 服务**：文档为纯设计文档，§0/§7 明确"本轮未调用任何付费/外部 AI 服务"；离线替身/mock 均标注"未接入/未验收"。运行时上下文无付费服务调用痕迹（`dl/`、`plan-contract/` 内同名文件与附件哈希一致，仅含文档对"付费/未接入"边界的讨论，非调用）。
- **敏感/真人声音/肖像/音乐"不接入"**：§4 明确标注，与 Agent Identity 硬约束一致。

### 4. 基线更正（issue 旧基线已过时）—— 通过，实测为真
- issue 旧基线"旧结构/无 tool/method/contract/仅 CLI 入口"与 `main@f10953d0` 实测不符，文档更正准确：
  - **tools**：`tools/tool_registry.py` 含 `discover`(L118)/`support_envelope`(L198)/`capability_catalog`(L212)/`provider_menu`(L249)/`provider_menu_summary`(L316)；`tools/{audio/tts_selector,graphics/image_selector,video/video_selector,capture/screen_capture_selector}.py` + `tools/cost_tracker.py`。
  - **method**：`skills/pipelines/*/*-director.md` 实测 91 个 + `.agents/skills/` 实测 994 个文件。
  - **contract**：`schemas/`（`pipelines/pipeline_manifest.schema.json`、`artifacts/`、`checkpoints/`、`tools/` 等 JSON Schema）+ `tests/contracts/`（`test_backlot_contract.py`、`test_resolve_blueprint_contract.py`、`test_phase0..3_contracts.py`、`test_pipeline_catalog.py`）+ `lib/resolve_blueprint.py`（`create_new_project`(L18)/`add_video_clip`(L21)/`add_audio_clip`(L22)/`save_new_project`(L23)，`Draft202012Validator` L12/L65）。
  - **backlot**：确为只读 FastAPI 看板（`server.py` "never writes to project directories"），非"仅 CLI/提示词入口"。

## 未覆盖项 / 局限
- "未调用付费/外部 AI" 以"设计文档性质 + 运行时上下文无调用痕迹 + 作者显式声明"佐证，非正向运行时追踪（本轮为设计/契约，无执行）。
- 未在本轮重跑 "15s 本地技术测试片" 渲染（`render_demo.py`/remotion-composer/`demo-props/*.json` 路径已确认存在，但作者既有的渲染验证属其自证，不在本草案审查范围，未重复执行）。
- 未核验 `pydantic`/`jsonschema` 运行时可导入（仅确认在 `requirements.txt` 基线声明）。
- 文档 §7 原始产物路径位于 lsit-285 worktree（`task-context-3699695277/deliverables/`），本 worktree 不可直接访问；以附件哈希复算为准，不影响结论。

## 风险
- `requirements.txt` 基线含付费云客户端依赖（`google-genai`、`openai`、`google-auth`），用于可选付费工具；文档 §4 正确将其界定为"未接入/需授权、不默认调用"，与本草案零付费/本地边界不冲突，供制片统筹知悉。

## 下一接收人
独立质检（d9095bea，已通过）→ 制片统筹（0640b2f5，整体验收）。父任务 LSIT-284 在整体验收前保持未完成，本任务不擅自关闭。
