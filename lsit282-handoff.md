## LSIT-282 续做交付（工程集成 d5dd01ea·绑定 worktree `agent/issue-tree/lsit-282`）

从 Phase 1 checkpoint 续做，**未重做 Phase 1**。Phase 2（伞仓库合并）+ Phase 3（整库 AGPLv3）已逐阶段提交可回滚 checkpoint，交付独立质检（非作者）复验。不以作者自检冒充通过。

### 目标
把 OpenReel 作为通用主工具并入 OpenMontage 构成伞仓库，整库转 AGPLv3；仅本地、零付费、无凭据、无付费 AI；不冒充真实 AI 服务已接入或生成质量已验收。

### 实际产物（均已在绑定 worktree 分支 `agent/issue-tree/lsit-282` 提交，HEAD `4bc7b97a`）
逐阶段可回滚 checkpoint（任一再次取消可从最新 checkpoint 续做）：
- `1186b27f` Phase 2a — `tool/` = 整个 OpenReel 源码（`git archive` of Phase 1 checkpoint `wip282-replay@84e74cf`）。
- `dfd8f9fc` Phase 2b — `method/` = 现 OpenMontage 全部内容（`git mv`，保留历史）；`remotion-composer` 并存顶层。
- `8374c574` Phase 2c — `contract/`（edit-spec）顶层契约层。
- `4bc7b97a` Phase 3 — 整库 AGPLv3（各子树 LICENSE，保留 OpenReel 第三方署名）。

### 最终结构（顶层，tracked）
`tool/`（OpenReel）+ `method/`（OpenMontage）+ `contract/`（edit-spec）+ `remotion-composer/`（并存）+ 根 `LICENSE`/`.gitignore`。

### 能力层保全 / 无误删（实测，非声明）
- `tool/` = **8597** 文件（`find` 与 `git ls-files` 均 8597；15 个被 `.gitignore` 命中但在 `84e74cf` 已跟踪的文件已 `git add -f` 强制补回，避免误删）。
- `method/` = **2082** 文件 = 原 OpenMontage 2124 − remotion-composer(41) − 根 .gitignore(1)；`git mv` 全为 rename，**无文件删除**。
- 5 apps（cloud/desktop/image/studio/web）+ 10 packages（agent/agent-runner/core/creation-agent/creation-bindings/creation-core/creation-schema/fxpkg/image-core/ui）全部在 `tool/`，一个不删。
- `remotion-composer` = 42（41 + 新增 LICENSE），并存顶层；`contract/` = 5。
- 合并已排除 `node_modules`/`.git`（`git archive` 天然排除；`tool/` 内无 `node_modules`/`.git`）。
- 整库 tracked = **10728**；工作树干净（仅本 run 的 context 文件 `.multica/`、`lsit282-desc.md`、`next-step.json`、`nextstep.json` 未跟踪，未提交）。

### AGPLv3（Phase 3，保留第三方署名）
- `tool/LICENSE`：MIT→AGPLv3，**保留 `Copyright (c) 2024-2026 Augustus Otu and Contributors`** + 追加 AGPLv3 条款（676 行）；sha256 `1a152608…`。
- 根 `LICENSE`：伞仓库 AGPLv3，注明 tool/method/contract/remotion-composer 及 OpenReel 署名（678 行）；sha256 `6083769c…`。
- `method/LICENSE`：原 OpenMontage AGPLv3（未改）。
- `remotion-composer/LICENSE`、`contract/LICENSE`：新增 AGPLv3 说明。
- 内容哈希：remotion-composer/LICENSE `2aa36144…`；contract/LICENSE `e5595874…`；全树内容哈希 `3b622fc4…`（`git ls-files|sort|xargs shasum|shasum`）。
- 依据已锁定决策：整库 AGPLv3（§13 SaaS copyleft 影响已知悉）为品牌/法律影响、非能力损失；不再复述、不再问。

### 命令与退出结果（实测，非虚报）
- `git archive 84e74cf | tar -x`（Phase 2a）exit 0；`git add -f tool` exit 0；`git ls-files tool`=8597。
- `git mv`（Phase 2b）exit 0；顶层 = `.gitignore/method/remotion-composer/tool`。
- `git add -A`+`git commit`（各 checkpoint）exit 0。
- 未运行 `tsc`/`tsup`/`vitest`：**故意不跑**（`openreel-lsit277` 未装依赖；按制片统筹指令，构建验证由独立质检装依赖后复验，不以作者自检当通过）。

### 未覆盖项 / 风险 / 待验证（明确，未冒充通过）
1. **构建未验证**：`tsc`/`tsup`/`vitest`（含 `command-llm.test.ts`）未运行——需独立质检装依赖后复验（非作者）。
2. **`contract/edit-spec` 内容为骨架**：`edit-spec.schema.json`/`example.json` 已创建并校验 JSON，但字段/取值/门禁**未定稿**，须制片统筹或独立质检依据实际流程最终确定；不得以骨架冒充正式契约。
3. **逐源文件头未改写**：各子树 `LICENSE` 已转 AGPLv3，但 8597+ OpenReel 源文件内嵌版权头**未逐文件改写**（体量大、风险高）；如整体验收要求逐源文件头，需单独派明确任务。
4. 真实 AI/付费服务未接入（本地 mock/离线替身须标注）；AGPLv3 为品牌/法律影响非能力损失。

### 阻塞与解除条件
- 无真实外部阻塞（纯机械改动 + LICENSE 头，无付费/无凭据/无联网）。
- 结构子决策（`remotion-composer` 并存顶层、根 `.gitignore` 保留、`contract/edit-spec` 骨架）均已在提交信息与 `contract/README.md` 记录，供 QC/制片统筹核对或调整；可调整项**不标 blocked**（可解决）。

### 验证证据（供独立质检复验）
- 分支/HEAD：`agent/issue-tree/lsit-282` @ `4bc7b97a`；4 个 checkpoint 见上。
- Phase 1 checkpoint 未动：`openreel-lsit277` 仍 `wip282-replay@84e74cf`（只读，未改）。
- 计数/哈希/结构见上（tool 8597、method 2082、remotion-composer 42、contract 5、整库 10728）。

### 状态与下一接收人
- 本议题置 **`in_review`**（作者已交付 Phase 2+3 机械成果，待独立质检复验；不以作者自检当通过）。
- **下一接收人：独立质检（非作者）**：装依赖复验 `tsc`/`tsup`/`vitest`（含 `command-llm.test.ts`）+ 5 apps/10 packages 完整 + `remotion-composer` 并存 + AGPLv3 头到位 + `.bak`/`test-lsit273/` 未入库 → 复验通过后交**制片统筹**整体验收。
- 不自行关闭父任务；不以运行结束替代验收。
