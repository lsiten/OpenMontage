## 目标
把 OpenReel 作为通用主工具并入 OpenMontage，构成伞仓库（monorepo），整库转 AGPLv3，并把 OpenReel 侧未提交 WIP 安全重放到权威线之上。仅本地、零付费、无凭据、无付费 AI；不冒充真实 AI 服务已接入或生成质量已验收。

## 当前状态（2026-10-25 续做·非重复失败尝试）
- **Phase 1（WIP 重放）已完成并核实**：`openreel-lsit277` 分支 `wip282-replay` @ `84e74cf`。真实解 `cli.ts` 冲突（b673cb6 为严格超集，取之而非回退 cost gate）；带入 3 个净新/改动文件（command-llm.ts 300 / command-llm.test.ts 113 / node-llm.ts +32），cli.ts 意图经 b673cb6 超集保全；`.bak` 与 `test-lsit273/` 已排除；工作树干净。
- **Phase 2（伞仓库合并）与 Phase 3（整库 AGPLv3）未做**：OpenMontage 主 `main@f10953d` 干净；无 `tool/`、`method/`、`contract/`。
- 首次工程运行（04:08→04:27）在 Phase 2 可行性/规模分析阶段被服务器取消（`task cancelled by server`，max_attempts=2 未自动重试）。工程已自行重派一次（04:38 起新运行，attempt 1）继续；本条为制片统筹协调续做，**不重复原失败尝试、不另起重复子任务、不与活动运行冲突**。

## 续做要求（修因：防再次取消丢进度）
- 从 Phase 1 checkpoint 续做，**不重做 Phase 1**（`84e74cf` 已入库）。
- Phase 2、Phase 3 **逐阶段提交可回滚 checkpoint**（每完成一步即 commit 到绑定 worktree 分支并登记路径/内容哈希/制作基线），确保任何再次取消都能保留进度、下一次从最新 checkpoint 续做。
- 合并 OpenReel 时**排除 `node_modules` 与 `.git`**（仅搬源码：5 apps + 10 packages 的源码），保持合并体量小、快；登记被排除项。
- 不重做 Phase 1；不以 mock 冒充冲突解决；不 stage/commit 无关文件。

## 已锁定决策（聊天已存，非采信作者自检）
- WIP 入库范围：提交 WIP，排除 `node-llm.ts.bak`（.bak 备份）与 `test-lsit273/`（scratch）。入库 = `cli.ts` + `node-llm.ts`（改）+ `command-llm.ts` + `command-llm.test.ts`（新，约 113 行）。
- 整库 AGPLv3：MIT→AGPLv3 已裁定接受（§13 SaaS copyleft 影响用户已知悉），不再复述、不再问。

## 基线（2026-10-25 实测，非声明）
- OpenMontage `main@f10953d`，LICENSE=AGPLv3，工作树干净。
- OpenReel 权威线 `lsit277` `main@b673cb6`；WIP 重放已在其上分支 `wip282-replay` @ `84e74cf`（Phase 1）。
- OpenReel WIP 线 `lsit273` `main@367d7e9`（`367d7e9` 为 `b673cb6` 祖先）。

## 范围（三步：Phase 1 已完成；续做 Phase 2→Phase 3，均在绑定 worktree）
1. [已完成] 提交 WIP：从 `lsit273@367d7e9` 重放到权威线 `b673cb6` 之上，真实解 `cli.ts` 冲突；只入库 4 项，排除 `.bak` 与 `test-lsit273/`。→ checkpoint `wip282-replay@84e74cf`。
2. [待做] 伞仓库合并：`OpenMontage/` 结构化为 `tool/`（整个 OpenReel：5 apps + 10 packages 源码，一个不删；排除 `node_modules`/`.git`）+ `method/`（现 OpenMontage 内容）+ `contract/`（edit-spec）；`remotion-composer` 并存（动画解说 niche），OpenReel 作通用主工具 → 能力层完全保全。
3. [待做] 整库 AGPLv3：MIT→AGPLv3（兼容、能力不丢），更新各子树 LICENSE 与头文件。

## 依赖
- 项目绑定 worktree：OpenMontage；OpenReel 权威线 lsit277（含 Phase 1 checkpoint）/ WIP 线 lsit273 只读读取，跨任务读取须核实路径/哈希/基线，禁止假定未提交产物自动共享。

## 产物
- [已完成] 重放后的 OpenReel 权威线（含 4 项 WIP，cli.ts 冲突已真实解决）= `wip282-replay@84e74cf`。
- [待做] 结构化后的伞仓库目录树（tool/ + method/ + contract/，remotion-composer 并存）。
- [待做] 整库 AGPLv3（各子树 LICENSE + 头文件）。
- 保留可回滚 diff；登记产物路径/内容哈希/制作基线。

## 证据（须记录实际命令、退出码，不虚报）
- `tsc` / `tsup` / `vitest` 实际运行 exit 0（含 command-llm.test.ts）。
- 成本门禁通过；无密钥/无私有素材/无付费 AI 调用；AGPLv3 头到位。
- 能力层无缺失：5 apps + 10 packages 全在，remotion-composer 并存。

## 验收条件
- 三步全部落地且证据 exit 0；WIP 仅入库 4 项；.bak 与 test-lsit273/ 未入库。
- 伞仓库目录结构正确、能力层完全保全、无文件误删。
- 整库 AGPLv3 到位。
- 由独立质检（非作者）复验通过，再交制片统筹整体验收；不以作者自检当通过。

## 边界
- 仅工程集成在授权范围内实施代码改动；不擅自 push/PR/合并/部署/发布/改外部权限/启动后台巡检。
- 未覆盖：真实 AI/付费服务未接入（本地 mock/离线替身须标注）；AGPLv3 为品牌/法律影响而非能力损失；WIP 重放须真实解 cli.ts 冲突（非 mock 冒充）。

## 下一接收人
工程集成交付 → 独立质检（非作者复验）→ 制片统筹（整体验收）。
