# PM 实现产物登记（LSIT-288 / 实现·工程集成 d5dd01ea）

## 制作基线
- 仓库：https://github.com/lsiten/OpenMontage.git
- 制作基线：`main@f10953d0`（`f10953d09bbdb2a400af6ba4b856b7d49d7846d8`）
- 绑定 worktree 分支：`agent/issue-tree/lsit-287`，HEAD `f1c315047d8f44103f0644afe0b4c91210e361d3`
- `git diff main..HEAD` 为空 → worktree 已跟踪内容 == 基线 `main@f10953d0`
- 本次改动全部为**未跟踪**新增（`pm/` + `tests/pm/`），未修改任何已跟踪基线文件（`git diff --stat HEAD` 为空）
- 契约依据：LSIT-285 附件 `LSIT-285-agentic-video-product-design.md`（id 01a171ec-…，sha256 `ecdde6209420c1b4f4577225ebd2516e50e8527f684ad0d08e90b41fdb554a51`，13629 字节，已核对一致）

## 产物（路径 / 内容 sha256）
> 相对绑定 worktree 根目录；全部未跟踪，保留可回滚差异，未 commit/push/PR。

### pm/（独立 PM 应用 + 对话入口）
- pm/__init__.py  117c94dece7a062161b8c6b49d04279c2577896aa2a10a4d8731ec5187ae5758
- pm/__main__.py  ad76b166b27c4a29d8a0360a9391243134ad2bc4b67312f15daabdb0656d4295
- pm/db.py  8d0318960ff3616c7da38069910110fc0c59a70aff49b3f3ec56aad307568612
- pm/schemas.py  514134e047de6813e4a4f47385a669a1ac88fd00ff802123d313ca7fc86555e1
- pm/pipeline_select.py  b1a833f3e2a7d0fc4ffe3bc27a7cbc4d59ab1f060eebed77d6203a394dea401c
- pm/capabilities.py  e372ddf6c89fc4356fe872e66876783ab3be809e967883e963a0477119ac5b90
- pm/store.py  5b422f8710dbed88cd56e09bbdda038abdeeb902c9bf3f4eaf107a3b93713350
- pm/chat.py  955dcbf54f974262c9de1e6d24c94643ee3453596b02b2dff70868f7fab323b4
- pm/server.py  0544626779e5dce3ce28fa143d2a96d9c1b6e41734429e20a546ef6e9a329ed8
- pm/ui/index.html  97a8017297e2f3bd67337b9ad14b17222eb740b1d728af61de93919013283929
- pm/ui/chat.html  0491d9a2123aaaff7a09161b5d58565c8f77f227be725b099aee6f9f35d95a7b
- pm/ui/detail.html  80b560a0359fa6a67b48c3c686489dde53e44f9f4653a61985c8e0a87cbeef72
- pm/ui/pm.css  6498f78adfc02b2026be752d5c69be8be2ec616c34a2df87b0336bd66baf9219
- pm/ui/pm.js  a0f2f7f7c931bdefc79b283e6b5e64f1b5a23e236953468b26d62d47d0a14c9a

### tests/pm/（新增测试 + 契约）
- tests/pm/conftest.py  0f7db060085affca68af5dc6d30e0678be7b4844343282d91b8baa37de97f928
- tests/pm/test_pm_store.py  622bab3eb1669b5338afb6ccbf73c55d62dcbb591d7fda911ce74e59f2b77708
- tests/pm/test_pm_chat.py  59d66d9b80d897fff08aca8a68cb9e9d6c1c6b8aff8c164aa85058f3599fd45e
- tests/pm/test_pm_contract.py  3947201fc1713e1d536ec1c3355af3362abf2f859fa0c0b0afb71156b62b4213
- tests/pm/test_pm_server.py  8afd23ec97d67755900f29eae8fab71f305e0d455f67a200b6e1396b198f7b0d

### 交付包
- deliver/pm-deliverable.tgz（pm/ + tests/pm/，排除 __pycache__）26918 字节
  sha256 `ef9fee3c645deaee3668b2b77444260bc778f95509503f0295c54231ee46ac39`

## 关键修复（本轮，仅 pm/ 未跟踪层）
1. pm/store.py：`_lock` 由非重入 `threading.Lock()` 改为 `threading.RLock()`。
   根因：`create_project` 持有 `_lock` 后调用 `_make_project_id` 再次获取同一非重入锁 →
   同线程自死锁 → 写路径永久挂起（上轮"hang"的真正根因，非进程争用）。
2. pm/store.py：`update_project` 的 SQL 占位符/参数错位修正。
   原 `args=[字段值, updated_by, _now()]` 对 `SET {fields}, updated_at=? WHERE project_id=?`
   错位 → 状态/预算更新实际匹配不到行（静默不更新）。改为 `args=[字段值, _now(), project_id]`
   （schema 无 updated_by 列，丢弃审计提示）。
3. pm/db.py：`connect()` 加 `check_same_thread=False`。
   单连接被 FastAPI 线程池跨线程复用 → 原 `sqlite3.ProgrammingError`（线程亲和）。
   RLock 序列化访问，跨线程安全。
4. pm/server.py：`/api/capabilities` 的 `local_available` 由 `c.status` 改为 `c.get("status")`
   （local 已是 model_dump 后的 dict 列表）。

## 未覆盖 / 诚实记录
- `scripts/backlot_simulate_run.py --fast` 失败（`CheckpointValidationError`：script 阶段跳过
  proposal 前置）。**为基线脚本既有缺陷**：该脚本与 `lib/checkpoint.py` 均为已跟踪基线文件，
  本轮未改动（`git diff --stat HEAD` 为空），非 pm/ 工作引入。工程缺陷仅记录，由队长派发修复任务。
- `render_demo.py` 完整渲染未跑（需 Node+Remotion 真实渲染，重/慢/可能联网；属 Remotion 运行时，
  非 pm/ 交付）。已跑 `render_demo.py --list`（列出 3 个 zero-key demo，OK）。
- 离线/未接入能力仅为"报告"，不代表真实 AI 服务已接入或生成质量已验收。

## 下一接收人
工程集成（d5dd01ea，实现/制作）→ 独立质检（d9095bea，非作者复验）→ 制片统筹（0640b2f5，整体验收）。
父任务 LSIT-284 在整体验收前保持未完成，本任务不擅自关闭父任务。
