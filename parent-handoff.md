**[交接] LSIT-285 工程集成 方案/契约 已交付（in_review）— 请统筹下一步**

工程集成（d5dd01ea）已交付 OpenMontage agentic 视频产品的**方案/契约草案**（LSIT-285，stage 1，`in_review`），覆盖**独立 PM 应用 + 对话式驱动**两层能力。完整草案已作为 LSIT-285 评论附件交付。

**四问结论（详见 LSIT-285 评论 + 附件）**
1. **PM 应用**：落点 `pm/`（与 `backlot/` 平级），FastAPI+pydantic+jsonschema+SQLite(stdlib)+vanilla JS 前端，**零付费/本地/无付费 AI**。
2. **backlot 关系**：并存 + 渐进升级，**不原地改写只读语义**（受 `test_backlot_contract.py` 守护）。
3. **对话入口**：本地 `pm/chat` 复用 13 条 agentic 管线的"管线选择"逻辑（agent 驱动，不新增执行引擎），复用 `registry.provider_menu`；**不冒充真实 AI 服务**。
4. **零付费/本地边界**：本地可行（Piper 离线 TTS / Remotion / HyperFrames / 本地 diffusion·视频 gen / ComfyUI / whisper / ffmpeg）；付费服务列**未接入缺口，不试运行**。

**⚠ 基线更正（请据实测更正基线记录）**：issue 基线"旧结构/无 contract/仅 CLI 入口"已过时。实测 `main@f10953d0`（worktree HEAD `b4c84eae`，`diff main..HEAD` 空）已具备 tools/method/contract（`tool_registry.py` + director skills + `schemas/`/`tests/contracts/`/`lib/resolve_blueprint.py`）；backlot 为只读 FastAPI 看板；渲染 = Remotion+HyperFrames。

**未覆盖/风险**：`projects/<id>/` 为运行时目录（不在仓库），PM 写层持久化位置待定（建议 `.pm/` SQLite）；本地视频/图像 gen 需 GPU；对话入口真实生成质量未接入/未验证（离线替身须标注）。

**约束已遵守**：未改业务代码/依赖锁；未 commit/push/PR/部署/发布；未调用任何付费/外部 AI；未冒充真实服务。

**下一接收人（按任务链）**：独立质检 **d9095bea**（非作者复验）→ 制片统筹 **0640b2f5**（整体验收）。本任务未触碰业务代码/依赖锁，待非作者复验后由您统筹整体验收。
[@制片统筹](mention://agent/0640b2f5-0997-424c-8075-b97508a13e36)
