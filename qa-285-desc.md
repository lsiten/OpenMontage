## 角色与授权
OpenMontage 视频制作小队·**独立质检**（d9095bea）。你是**非作者**复审；制片统筹（0640b2f5）是唯一整体验收负责人。本任务**只复审 LSIT-285 的方案/契约草案，不改业务代码/依赖锁、不 commit/push/PR/部署/发布**。

## 任务
独立复验工程集成（d5dd01ea）交付的 **LSIT-285 方案/契约草案**（父任务 LSIT-284，stage 1 已 in_review）。**不采信作者自检**，以实测为准。

## 待验产物
- 附件：`LSIT-285-agentic-video-product-design.md`（附件 id `01a171ec-f743-71a2-bbb7-7a9cc2855407`，13629 字节）。
- 内容哈希（须自行复算一致）：sha256 `ecdde6209420c1b4f4577225ebd2516e50e8527f684ad0d08e90b41fdb554a51`。
- 制作基线：`main@f10953d0`（worktree 分支 `agent/issue-tree/lsit-284` HEAD `b4c84eae`，`git diff main..HEAD --stat` 为空）；AGPLv3；2026-10-25 实测。

## 须独立核实（逐条，附命令/退出码/证据，不臆造）
1. **产物真实可评审**：附件可下载、哈希与上表一致、内容完整（§0 基线核实 + §1–§4 四问 + §5 风险 + §6 验收 + §7 登记 + §8 下一接收人）。
2. **四问均有明确、可评审结论**（§1–§4）：① 落点/技术栈（`pm/` + FastAPI/pydantic/jsonschema/SQLite(stdlib)/vanilla JS，零付费本地无付费 AI）；② backlot 关系（并存+渐进升级，不原地改写只读语义，受 `test_backlot_contract.py` 守护）；③ 对话入口（本地 `pm/chat` 复用 13 条 agentic 管线"管线选择"逻辑，不新增执行引擎，不冒充真实 AI 服务，Bloome 为 external 未复用）；④ 零付费/本地边界（本地可行 vs 付费=未接入缺口不试运行，成本/授权边界清晰）。
3. **约束遵守（实测，不采信作者声明）**：
   - 未改业务代码/依赖锁：`git status`、`git diff main..HEAD` 是否只含运行时上下文（`.multica/` 等）而无业务源码/`requirements*.txt`/锁文件改动。
   - 未 commit/push/PR/部署/发布：HEAD 是否为 no-op 本地 baseline（`b4c84eae` 仅在本 worktree 分支、未 push、diff 空）。
   - 未调用任何付费/外部 AI；未冒充真实 AI 服务（离线替身/mock 是否标注"未接入/未验收"）。
   - 敏感/真人声音/肖像/音乐是否"不接入"。
4. **基线更正**：issue 旧基线"旧结构/无 tool/method/contract/仅 CLI 入口"是否已过时；实测 `main@f10953d0` 是否已具备 tools（`tool_registry.py`）/method（director skills + `.agents/skills/`）/contract（`schemas/` + `tests/contracts/` + `lib/resolve_blueprint.py`），backlot 是否为只读 FastAPI 看板。

## 验收条件
- 逐条给出通过/退回结论 + 版本/数据时间/命令/退出码/证据/未覆盖项；不以"运行结束"或作者声明当通过。
- **通过**：四问结论可评审、约束全遵守、产物真实 → 报制片统筹（0640b2f5）整体验收。
- **退回**：列出不通过项，交回原负责人工程集成（d5dd01ea）逐项修复、复测并重新提交，保持相关工作未完成（可修复问题不标 blocked）。

## 产物与交付
- 复审结论（通过/退回 + 逐项证据）写入隔离产物路径；面向用户的文件经 Multica 附件交付；登记路径/内容哈希/制作基线。

## 下一接收人
独立质检（d9095bea）→ 制片统筹（0640b2f5，整体验收）；父任务 LSIT-284 在整体验收前保持未完成，不擅自关闭。
